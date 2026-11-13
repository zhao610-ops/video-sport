"""用可手工核算的位置检查指标口径、缺失数据及导出一致性。"""

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from sports.common.tactics import calculate_tactics
from examples.soccer.tactics import export_tactics


def position(track_id, team_id, x, y, role='player', valid=True):
    return {'track_id': track_id, 'team_id': team_id, 'x_norm': x, 'y_norm': y,
            'role': role, 'coordinate_valid': valid}


class TacticsTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            'schema_version': '1.0', 'summary': {'status': 'complete'},
            'metadata': {'source_video': '测试.mp4', 'pitch_profile': {'status': 'unknown'},
                         'template_cm': {'length': 12000, 'width': 7000}},
            'frames': [
                {'frame_index': 0, 'timestamp_s': 0., 'mapping': {'valid': True},
                 'positions': [position(1, 0, 10, 20), position(2, 0, 30, 60),
                               position(3, 0, 2, 50, 'goalkeeper'),
                               position(4, 1, 70, 30), position(5, 1, 80, 70),
                               position(6, 0, 99, 99, valid=False), position(7, None, 50, 50),
                               position(8, 1, 50, 50, 'referee')]},
                {'frame_index': 1, 'timestamp_s': .04, 'mapping': {'valid': False},
                 'positions': [position(1, 0, 10, 20), position(2, 0, 30, 60)]},
                {'frame_index': 2, 'timestamp_s': .08, 'mapping': {'valid': True},
                 'positions': [position(1, 0, 10, 20)]},
            ],
        }

    def test_outfield_center_width_and_length_axes(self):
        original = copy.deepcopy(self.data)
        result = calculate_tactics(self.data, include_goalkeepers=False)
        a, b = result['team_frames'][:2]
        self.assertEqual((a['center_x'], a['center_y']), (20., 40.))
        self.assertEqual((a['width'], a['longitudinal_span']), (40, 20))
        self.assertEqual(a['visible_count'], 2)
        self.assertEqual((b['center_x'], b['center_y']), (75., 50.))
        self.assertEqual(self.data, original)

    def test_goalkeeper_policy_is_explicit_and_changes_span(self):
        result = calculate_tactics(self.data, include_goalkeepers=True)
        a = result['team_frames'][0]
        self.assertEqual(a['visible_count'], 3)
        self.assertEqual(a['goalkeeper_count'], 1)
        self.assertEqual(a['center_x'], 14.)
        self.assertAlmostEqual(a['center_y'], 130 / 3)
        self.assertEqual(a['longitudinal_span'], 28)
        self.assertTrue(result['metadata']['include_goalkeepers'])
        with self.assertRaises(ValueError):
            calculate_tactics(self.data, include_goalkeepers=None)

    def test_invalid_mapping_and_insufficient_players_stay_missing(self):
        result = calculate_tactics(self.data, include_goalkeepers=False)
        self.assertEqual(result['summary']['team_frame_count'], 6)
        self.assertEqual(result['summary']['available_team_frames'], 2)
        for row in result['team_frames'][2:]:
            self.assertFalse(row['available'])
            self.assertIsNone(row['center_x'])
            self.assertIsNone(row['width'])
        self.assertEqual(result['team_frames'][2]['reason'], 'frame_mapping_invalid')
        self.assertEqual(result['team_frames'][4]['visible_count'], 1)
        self.assertEqual(result['team_frames'][4]['reason'], 'insufficient_players')

    def test_duplicate_unknown_and_bad_coordinates_are_excluded(self):
        self.data['frames'][0]['positions'].extend([
            position(1, 0, 40, 50), position(9, 0, float('nan'), 10),
            position(10, 0, -1, 50), position(11, False, 20, 30),
        ])
        result = calculate_tactics(self.data, include_goalkeepers=False)
        self.assertFalse(result['team_frames'][0]['available'])
        self.assertEqual(result['team_frames'][0]['track_ids'], [2])
        self.assertEqual(result['summary']['excluded_observations']['duplicate_track_id'], 2)
        self.assertEqual(result['summary']['excluded_observations']['invalid_coordinate_value'], 2)

    def test_export_keeps_missing_cells_and_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'analysis.json'
            path.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
            result = export_tactics(path, root / 'metrics', include_goalkeepers=False)
            with open(root / 'metrics/metrics.json', encoding='utf-8') as stream:
                saved = json.load(stream)
            with open(root / 'metrics/metrics.csv', encoding='utf-8', newline='') as stream:
                csv_rows = list(csv.DictReader(stream))
            self.assertEqual(saved['team_frames'], result['team_frames'])
            self.assertEqual(len(csv_rows), 6)
            self.assertEqual(csv_rows[2]['width'], '')
            self.assertEqual(json.loads(csv_rows[0]['track_ids']), [1, 2])
            self.assertIn('排除守门员', (root / 'metrics/report.html').read_text(encoding='utf-8'))
            with self.assertRaises(FileExistsError):
                export_tactics(path, root / 'metrics', include_goalkeepers=True)

    def test_bad_timestamps_and_minimum_are_rejected(self):
        with self.assertRaises(ValueError):
            calculate_tactics(self.data, include_goalkeepers=False, min_players=1)
        self.data['frames'][1]['timestamp_s'] = 0.
        with self.assertRaises(ValueError):
            calculate_tactics(self.data, include_goalkeepers=False)

    def test_impossible_outfield_count_does_not_make_a_span(self):
        self.data['frames'][0]['positions'] = [position(i, 0, i, i) for i in range(11)]
        excluded = calculate_tactics(self.data, include_goalkeepers=False)['team_frames'][0]
        self.assertFalse(excluded['available'])
        self.assertEqual(excluded['reason'], 'player_count_exceeds_limit')
        self.assertIsNone(excluded['width'])
        included = calculate_tactics(self.data, include_goalkeepers=True)['team_frames'][0]
        self.assertFalse(included['available'])
        self.data['frames'][0]['positions'][-1]['role'] = 'goalkeeper'
        included = calculate_tactics(self.data, include_goalkeepers=True)['team_frames'][0]
        self.assertTrue(included['available'])


if __name__ == '__main__':
    unittest.main()
