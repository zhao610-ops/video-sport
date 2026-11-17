"""验证本地统计、工具调用往返及错误脱敏，不使用真实密钥或联网。"""

import copy
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from sports.common.deepseek_agent import DeepSeekClient, DeepSeekError, load_local_env, run_agent
from sports.common.tactical_tools import TacticalTools


def dataset():
    rows = []
    for index, width in enumerate((20., 40., None)):
        for team in (0, 1):
            rows.append({'frame_index': index, 'timestamp_s': index*.04, 'team_id': team,
                         'available': width is not None,
                         'reason': 'ok' if width is not None else 'frame_mapping_invalid',
                         'visible_count': 5 if width is not None else 0,
                         'center_x': 30. if width is not None else None,
                         'center_y': 50. if width is not None else None,
                         'width': width, 'longitudinal_span': 10. if width is not None else None})
    return {'schema_version': 'tactics-1.0', 'team_frames': rows,
            'summary': {'frame_count': 3},
            'metadata': {'source_video': '/private/local-only/video.mp4', 'include_goalkeepers': False,
                         'min_players': 2, 'source_analysis_status': 'complete',
                         'pitch_profile': {'status': 'reference'},
                         'metric_definitions': {'local_path': '/private/local-only/metrics.json'}}}


def tool_call(name, arguments, identifier='call-1'):
    return {'content': None, 'tool_calls': [{'id': identifier, 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False)}}]}


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def complete(self, messages, tools, tool_choice):
        self.requests.append(copy.deepcopy({'messages': messages, 'tool_choice': tool_choice}))
        return next(self.responses)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tools = TacticalTools(dataset())

    def test_summary_does_not_treat_missing_as_zero(self):
        summary = self.tools.summarize(0)
        self.assertEqual(summary['statistics']['width']['mean'], 30.)
        self.assertEqual(summary['available_frames'], 2)
        self.assertAlmostEqual(summary['available_ratio'], 2/3)
        self.assertNotIn('/private/local-only', json.dumps(self.tools.overview()))
        self.assertEqual(self.tools.summarize(0, 1, 2)['statistics']['width']['mean'], None)

    def test_windows_are_half_open_and_differences_are_points(self):
        result = self.tools.compare(0, 0., .04, .04, .08)
        self.assertEqual(result['window_a']['selected_frames'], 1)
        self.assertEqual(result['mean_difference_b_minus_a']['width'], 20.)
        self.assertFalse(result['windows_overlap'])
        for arguments in ({'team_id': True}, {'team_id': 0, 'start_s': float('nan')},
                          {'team_id': 0, 'filename': '/private/local-only/file'}):
            with self.assertRaises(ValueError):
                self.tools.execute('summarize_team', arguments)
        with self.assertRaises(ValueError):
            self.tools.compare(0, None, .04, .04, .08)

    def test_tool_round_trip_and_evidence(self):
        fake = FakeClient([tool_call('get_dataset_overview', {}),
                           tool_call('summarize_team', {'team_id': 0}, 'call-2'),
                           {'content': '球队 0 的平均横向宽度为球场宽度的 30%。可用帧为 2/3。[E2]'}])
        result = run_agent('球队 0 的宽度是多少？', self.tools, fake)
        self.assertEqual(len(result['evidence']), 2)
        self.assertTrue(all(x['success'] for x in result['evidence']))
        self.assertEqual(fake.requests[0]['tool_choice']['function']['name'], 'get_dataset_overview')
        self.assertNotIn('/private/local-only', json.dumps(fake.requests, ensure_ascii=False))
        self.assertEqual(fake.requests[-1]['messages'][-1]['role'], 'tool')

    def test_unknown_tool_is_not_executed_and_can_recover(self):
        fake = FakeClient([tool_call('run_shell', {'command': 'invalid-command'}),
                           tool_call('get_dataset_overview', {}, 'call-2'),
                           tool_call('summarize_team', {'team_id': 0}, 'call-3'),
                           {'content': '平均横向宽度为 30%。[E3]'}])
        result = run_agent('查询宽度', self.tools, fake)
        self.assertFalse(result['evidence'][0]['success'])
        self.assertEqual(result['evidence'][0]['arguments'], {})
        self.assertEqual(result['evidence'][0]['tool'], 'unknown_tool')

    def test_unsupported_citation_is_repaired_and_rounds_are_bounded(self):
        fake = FakeClient([tool_call('get_dataset_overview', {}),
                           tool_call('summarize_team', {'team_id': 0}, 'call-2'),
                           {'content': '宽度为 999%。[E99]'},
                           {'content': '平均宽度为 30%。[E2]'}])
        self.assertIn('[E2]', run_agent('查询宽度', self.tools, fake)['answer'])
        bounded = FakeClient([{'content': '没有工具依据的回答'}] * 2)
        with self.assertRaises(DeepSeekError):
            run_agent('查询宽度', self.tools, bounded, max_rounds=2)

    def test_http_error_does_not_echo_secret_or_response(self):
        secret = 'test-token-placeholder'
        error = urllib.error.HTTPError('https://api.deepseek.com/chat/completions', 401,
                                       'raw-error-' + secret, {}, io.BytesIO(secret.encode()))
        client = DeepSeekClient(api_key=secret)
        with patch('urllib.request.OpenerDirector.open', side_effect=error):
            with self.assertRaises(DeepSeekError) as captured:
                client.complete([], [], 'auto')
        self.assertIn('401', str(captured.exception))
        self.assertNotIn(secret, str(captured.exception))

    def test_unexpected_secret_in_answer_is_not_returned(self):
        secret = 'test-token-placeholder'
        fake = FakeClient([tool_call('get_dataset_overview', {}),
                           tool_call('summarize_team', {'team_id': 0}, 'call-2'),
                           {'content': secret + ' [E2]'}])
        fake.api_key = secret
        with self.assertRaises(DeepSeekError) as captured:
            run_agent('查询宽度', self.tools, fake)
        self.assertNotIn(secret, str(captured.exception))

    def test_client_body_and_env_loader_do_not_expose_credentials(self):
        secret = 'test-token-placeholder'
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': '回答'}}]}).encode()
        with patch('urllib.request.OpenerDirector.open', return_value=Response()) as opened:
            self.assertEqual(DeepSeekClient(api_key=secret).complete([], [], 'auto')['content'], '回答')
            request = opened.call_args.args[0]
            self.assertNotIn(secret, request.data.decode())
            self.assertEqual(request.full_url, 'https://api.deepseek.com/chat/completions')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('DEEPSEEK_API_KEY="test-token-placeholder"\nOTHER_VALUE=ignored\n', encoding='utf-8')
            with patch.dict(os.environ, {}, clear=True):
                load_local_env(path)
                self.assertEqual(os.environ['DEEPSEEK_API_KEY'], secret)
                self.assertNotIn('OTHER_VALUE', os.environ)


if __name__ == '__main__':
    unittest.main()
