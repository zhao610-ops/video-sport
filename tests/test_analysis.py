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


if __name__ == '__main__':
    unittest.main()
