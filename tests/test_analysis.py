"""用已知几何关系检查映射、异常标记和数据持久化。"""

import csv
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from sports.common.analysis import (
    AnalysisWriter, MappingSettings, fit_mapping, load_pitch_profile, map_position,
)
from examples.soccer.report import render_report
from examples.soccer.evaluate import compare_settings
from examples.soccer.review import build_review
from examples.soccer.remap import remap


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.config = load_pitch_profile()
        self.settings = MappingSettings()
        self.target = np.asarray(self.config.vertices, dtype=float)
        self.inverse = np.array([[.1, .015, 100], [.003, .08, 70], [.00001, .000005, 1.]])
        self.xy = cv2.perspectiveTransform(self.target.reshape(-1, 1, 2), self.inverse).reshape(-1, 2)

    def test_outliers_are_rejected_and_coordinates_recovered(self):
        xy = self.xy.copy()
        xy[:4] += [200, -100]
        matrix, quality = fit_mapping(xy, np.ones(32), self.config, self.settings)
        self.assertTrue(quality['valid'])
        self.assertLess(quality['inliers'], 32)
        real = np.array([[[self.config.length * .3, self.config.width * .6]]])
        pixel = cv2.perspectiveTransform(real, self.inverse)[0, 0]
        x, y, valid, _ = map_position(pixel, matrix, self.config)
        self.assertTrue(valid)
        self.assertAlmostEqual(x, 30, places=3)
        self.assertAlmostEqual(y, 60, places=3)

    def test_missing_low_confidence_and_collinear_points(self):
        for xy, conf in (([], []), (self.xy, np.zeros(32)),
                         (np.column_stack([np.arange(32) + 10] * 2), np.ones(32))):
            matrix, quality = fit_mapping(xy, conf, self.config, self.settings)
            self.assertIsNone(matrix)
            self.assertFalse(quality['valid'])

    def test_out_of_bounds_is_preserved_and_infinity_is_empty(self):
        x, y, valid, reason = map_position([-10, 200], np.eye(3), self.config)
        self.assertLess(x, 0)
        self.assertFalse(valid)
        self.assertEqual(reason, 'out_of_bounds')
        self.assertEqual(map_position([1, 2], np.zeros((3, 3)), self.config)[:2], (None, None))

    def test_region_support_rejects_midfield_only_fit(self):
        xy = self.xy.copy()
        confidence = np.zeros(32)
        confidence[[0, 9, 13, 14, 15, 16, 30, 31]] = 1
        xy[0] += [500, 600]
        xy[9] += [700, 400]
        settings = MappingSettings(require_region_support=True)
        matrix, quality = fit_mapping(xy, confidence, self.config, settings)
        self.assertIsNone(matrix)
        self.assertEqual(quality['reason'], 'insufficient_region_support')

    def test_structural_policy_and_remap_preserve_original_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {
                'schema_version': '1.0', 'summary': {'status': 'complete'},
                'metadata': {'source_video': '测试.mp4', 'pitch_profile': self.profile,
                             'template_cm': {'length': self.config.length, 'width': self.config.width,
                                             'penalty_box_length': self.config.penalty_box_length,
                                             'penalty_box_width': self.config.penalty_box_width},
                             'mapping_settings': vars(self.settings)},
                'frames': [{'frame_index': 0, 'timestamp_s': 0.,
                            'keypoints': {'xy': self.xy.tolist(), 'confidence': [1.] * 32},
                            'positions': [dict.fromkeys(AnalysisWriter.fields)]}],
            }
            pixel = cv2.perspectiveTransform(
                np.array([[[self.config.length * .3, self.config.width * .6]]]), self.inverse)[0, 0]
            data['frames'][0]['positions'][0].update(frame_index=0, timestamp_s=0., track_id=7,
                                                    role='player', team_id=1, image_x=float(pixel[0]),
                                                    image_y=float(pixel[1]), coordinate_valid=False)
            source = root / 'source.json'
            original = json.dumps(data, ensure_ascii=False)
            source.write_text(original, encoding='utf-8')
            remap(source, root / 'result', anchor_policy='structural', require_region_support=True)
            with open(root / 'result' / 'analysis.json', encoding='utf-8') as stream:
                result = json.load(stream)
            frame = result['frames'][0]
            self.assertEqual(frame['positions'][0]['track_id'], 7)
            self.assertEqual(frame['positions'][0]['team_id'], 1)
            self.assertAlmostEqual(frame['positions'][0]['x_norm'], 30., places=3)
            self.assertAlmostEqual(frame['positions'][0]['y_norm'], 60., places=3)
            self.assertTrue(frame['positions'][0]['coordinate_valid'])
            self.assertTrue(all(i not in frame['mapping']['inlier_keypoint_indices']
                                for i in (10, 11, 18, 19, 30, 31)))
            self.assertEqual(source.read_text(encoding='utf-8'), original)

    def test_csv_json_empty_frames_and_offline_report(self):
        with tempfile.TemporaryDirectory() as directory:
            metadata = {'source_video': '测试.mp4', 'pitch_profile': self.profile}
            writer = AnalysisWriter(directory, metadata)
            writer.add_frame(0, 0., {'valid': False, 'reason': 'missing_keypoints'}, [])
            row = dict.fromkeys(AnalysisWriter.fields)
            row.update(frame_index=1, timestamp_s=.04, track_id=7, role='player', team_id=0,
                       x_norm=30., y_norm=60., coordinate_valid=True, invalid_reason='ok')
            writer.add_frame(1, .04, {'valid': True, 'reason': 'ok'}, [row])
            invalid = dict(row, frame_index=2, timestamp_s=.08, x_norm=130.,
                           coordinate_valid=False, invalid_reason='out_of_bounds')
            writer.add_frame(2, .08, {'valid': True, 'reason': 'ok'}, [invalid])
            restored = dict(row, frame_index=3, timestamp_s=.12)
            writer.add_frame(3, .12, {'valid': True, 'reason': 'ok'}, [restored])
            writer.close('complete')
            with open(Path(directory) / 'analysis.json', encoding='utf-8') as stream:
                data = json.load(stream)
            with open(Path(directory) / 'positions.csv', encoding='utf-8', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(data['frames']), 4)
            self.assertEqual(len(rows), 3)
            self.assertEqual(data['frames'][1]['positions'][0]['track_id'], int(rows[0]['track_id']))
            render_report(Path(directory) / 'analysis.json', Path(directory) / 'report.html')
            self.assertTrue((Path(directory) / 'report.html').is_file())
            report = (Path(directory) / 'report.html').read_text(encoding='utf-8')
            self.assertNotIn('<line x1=', report)
            self.assertIn('其中 2 条坐标有效', report)
            with self.assertRaises(FileExistsError):
                AnalysisWriter(directory, metadata)

    def test_reference_dimensions_are_not_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'profile.json'
            p.write_text(json.dumps({'status': 'reference', 'length_m': 105, 'width_m': 68,
                                     'note': '人工提供的参考尺寸'}, ensure_ascii=False), encoding='utf-8')
            profile, config = load_pitch_profile(p)
            self.assertEqual(profile['status'], 'reference')
            self.assertEqual(config.length, 10500)
            p.write_text('{"status":"reference","length_m":111,"width_m":null}', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_pitch_profile(p)

    def test_compare_uses_identical_observations_without_models(self):
        pixel = cv2.perspectiveTransform(
            np.array([[[self.config.length * .3, self.config.width * .6]]]), self.inverse)[0, 0]
        data = {
            'schema_version': '1.0', 'summary': {'status': 'complete'},
            'metadata': {'source_video': '测试.mp4',
                         'template_cm': {'length': self.config.length, 'width': self.config.width,
                                         'penalty_box_length': self.config.penalty_box_length,
                                         'penalty_box_width': self.config.penalty_box_width},
                         'mapping_settings': vars(self.settings)},
            'frames': [{'frame_index': 0, 'keypoints': {'xy': self.xy.tolist(), 'confidence': [1.] * 32},
                        'positions': [{'track_id': 1, 'image_x': float(pixel[0]), 'image_y': float(pixel[1])}]}],
        }
        result = compare_settings(data, [8., 16.])
        self.assertEqual([x['valid_observations'] for x in result['results']], [1, 1])
        self.assertTrue(all(x['accepted_frame_inlier_error_median_px'] < .01 for x in result['results']))
        del data['frames'][0]['keypoints']
        with self.assertRaises(ValueError):
            compare_settings(data, [8.])

    def test_review_extracts_requested_frames_without_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = cv2.VideoWriter(str(root / 'source.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), 25., (80, 60))
            self.assertTrue(video.isOpened())
            for _ in range(3):
                video.write(np.zeros((60, 80, 3), dtype=np.uint8))
            video.release()
            data = {'metadata': {'source_video': str(root / 'source.mp4')},
                    'frames': [{'frame_index': i, 'timestamp_s': i / 25.,
                                'mapping': {'valid': False, 'reason': 'missing_keypoints'},
                                'positions': []} for i in range(3)]}
            path = root / 'analysis.json'
            path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            build_review(path, root / 'review.html', sample_count=3)
            content = (root / 'review.html').read_text(encoding='utf-8')
            self.assertEqual(content.count('data:image/jpeg;base64,'), 3)
            self.assertNotIn('DATA_PLACEHOLDER', content)
            build_review(path, root / 'selected.html', frame_indices=[2, 0, 2])
            self.assertEqual((root / 'selected.html').read_text(encoding='utf-8').count('data:image/jpeg;base64,'), 2)
            with self.assertRaises(ValueError):
                build_review(path, root / 'bad.html', frame_indices=[999])


if __name__ == '__main__':
    unittest.main()
