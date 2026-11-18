"""用可手算的图像候选检查足球关联与附加数据一致性。"""

import json
import tempfile
import unittest
from pathlib import Path

from sports.common.ball_tracking import ObservedBallTracker, tile_origins, suppress_duplicates
from sports.common.ball_data import file_sha256, load_ball_data


def candidate(x, y, confidence=.9):
    return {'bbox_xyxy': [x-2, y-2, x+2, y+2], 'confidence': confidence}


class BallTrackingTests(unittest.TestCase):
    def test_association_prefers_nearby_observation_over_distant_false_positive(self):
        tracker = ObservedBallTracker(1000, 600)
        first = tracker.update(0, [candidate(100, 200)])
        second = tracker.update(1, [candidate(108, 201, .6), candidate(800, 500, .99)])
        self.assertEqual((second['image_x'], second['image_y']), (108, 201))
        self.assertEqual(second['segment_id'], first['segment_id'])
        self.assertEqual(second['tracking_status'], 'associated')

    def test_missing_does_not_emit_predictions_and_breaks_segment(self):
        tracker = ObservedBallTracker(1000, 600)
        first = tracker.update(0, [candidate(100, 200)])
        missing = tracker.update(1, [])
        self.assertFalse(missing['detected'])
        self.assertIsNone(missing['image_x'])
        self.assertIsNone(missing['confidence'])
        reacquired = tracker.update(2, [candidate(110, 200)])
        self.assertGreater(reacquired['segment_id'], first['segment_id'])

    def test_large_jump_rejected_then_reacquired_or_reset_by_cut(self):
        tracker = ObservedBallTracker(1000, 600, max_gap=2)
        tracker.update(0, [candidate(100, 200)])
        self.assertEqual(tracker.update(1, [candidate(800, 500)])['tracking_status'], 'association_rejected')
        tracker.update(2, [])
        self.assertTrue(tracker.update(3, [candidate(800, 500)])['detected'])
        cut = tracker.update(4, [candidate(100, 200)], scene_changed=True)
        self.assertTrue(cut['detected'])
        self.assertEqual(cut['tracking_status'], 'reacquired')

    def test_bad_candidates_and_reversed_frames(self):
        tracker = ObservedBallTracker(1000, 600)
        result = tracker.update(0, [candidate(10, 20, .1), candidate(10, 20, float('nan')),
                                    candidate(-1, 20), candidate(10, 20, True)])
        self.assertFalse(result['detected'])
        with self.assertRaises(ValueError):
            tracker.update(0, [])

    def test_cut_without_detection_still_resets_motion_history(self):
        tracker = ObservedBallTracker(1000, 600)
        tracker.update(0, [candidate(100, 200)])
        tracker.update(1, [], scene_changed=True)
        self.assertTrue(tracker.update(2, [candidate(900, 500)])['detected'])

    def test_tiles_cover_edges_and_nms_deduplicates(self):
        self.assertEqual(tile_origins(1920), [0, 512, 1024, 1280])
        self.assertEqual(tile_origins(1080), [0, 440])
        self.assertEqual(tile_origins(320), [0])
        boxes = [candidate(100, 100, .8), candidate(100.5, 100.5, .9), candidate(200, 200)]
        self.assertEqual(len(suppress_duplicates(boxes)), 2)


class BallDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.video = self.root/'video.mp4'
        self.video.write_bytes(b'test-video')
        self.analysis = {'frames': [{'frame_index': 0, 'timestamp_s': 0., 'mapping': {'valid': True}},
                                    {'frame_index': 1, 'timestamp_s': .04, 'mapping': {'valid': False}}]}
        self.analysis_path = self.root/'analysis.json'
        self.analysis_path.write_text(json.dumps(self.analysis), encoding='utf-8')
        self.path = self.root/'ball.json'
        tracker = ObservedBallTracker(1000, 600)
        records = []
        for i, boxes in enumerate(([candidate(100, 200)], [])):
            row = tracker.update(i, boxes)
            row.update(frame_index=i, timestamp_s=i*.04, x_norm=10. if i == 0 else None,
                       y_norm=20. if i == 0 else None, projection_valid=i == 0,
                       projection_reason='ok' if i == 0 else 'ball_not_detected')
            records.append(row)
        self.data = {'schema_version': 'ball-1.0', 'summary': {'status': 'complete'},
                     'metadata': {'source_analysis_sha256': file_sha256(self.analysis_path),
                                  'source_video_sha256': file_sha256(self.video),
                                  'image_size': {'width': 1000, 'height': 600}}, 'frames': records}

    def tearDown(self):
        self.temp.cleanup()

    def load(self):
        self.path.write_text(json.dumps(self.data), encoding='utf-8')
        return load_ball_data(self.path, self.analysis_path, self.video, self.analysis)

    def test_matching_data_preserves_missing_and_never_claims_ground_truth(self):
        result = self.load()
        self.assertTrue(result['available'])
        self.assertEqual(result['summary']['detected_frames'], 1)
        self.assertFalse(result['frames'][0]['grounded_verified'])
        self.assertIsNone(result['frames'][1]['image_x'])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_changed_video_or_analysis_is_rejected(self):
        self.video.write_bytes(b'different-video')
        self.assertFalse(self.load()['available'])
        self.data['metadata']['source_video_sha256'] = file_sha256(self.video)
        self.analysis_path.write_text('different-analysis', encoding='utf-8')
        self.assertFalse(self.load()['available'])

    def test_partial_and_misaligned_results_are_rejected(self):
        self.data['summary']['status'] = 'incomplete'
        self.assertFalse(self.load()['available'])
        self.data['summary']['status'] = 'complete'
        self.data['frames'][1]['timestamp_s'] = .08
        self.assertFalse(self.load()['available'])

    def test_invalid_frame_cannot_claim_valid_projection_or_predicted_detection(self):
        self.data['frames'][1]['projection_valid'] = True
        self.assertFalse(self.load()['available'])
        self.data['frames'][1]['projection_valid'] = False
        self.data['frames'][1]['image_x'] = 100
        self.assertFalse(self.load()['available'])


if __name__ == '__main__':
    unittest.main()
