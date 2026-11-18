"""使用临时视频与可手算坐标检查本机工作台，不调用真实模型。"""

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from examples.soccer.web import Workspace, make_handler
from sports.common.deepseek_agent import DeepSeekError
from tests.test_tactics import position


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        video = root/'test.mp4'
        video.write_bytes(b'0123456789abcdef')
        data = {'schema_version': '1.0', 'summary': {'status': 'complete'},
                'metadata': {'source_video': str(video), 'fps': 25,
                             'pitch_profile': {'status': 'reference'},
                             'template_cm': {'length': 10500, 'width': 6800}},
                'frames': [
                    {'frame_index': 0, 'timestamp_s': 0., 'mapping': {'valid': True, 'reason': 'ok'},
                     'positions': [position(1, 0, 10, 20), position(2, 0, 30, 60),
                                   position(3, 0, 1, 50, role='goalkeeper')]},
                    {'frame_index': 1, 'timestamp_s': .04,
                     'mapping': {'valid': False, 'reason': 'insufficient_keypoints'},
                     'positions': [position(1, 0, 10, 20)]},
                ]}
        analysis = root/'analysis.json'
        analysis.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        with patch('examples.soccer.web.DeepSeekClient', return_value=type('Client', (), {'model': 'deepseek-flash'})()):
            self.workspace = Workspace(analysis, output_dir=root/'answers')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.workspace))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, method='GET', body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=4)
        conn.request(method, path, body=body, headers=headers or {})
        result = conn.getresponse()
        status, response_headers, payload = result.status, dict(result.getheaders()), result.read()
        conn.close()
        return status, response_headers, payload

    def test_real_data_missing_frames_and_goalkeeper_policy(self):
        status, _, body = self.request('/api/dataset')
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertNotIn(self.temp.name, body.decode())
        self.assertEqual(data['frames'][1]['positions'], [])
        self.assertEqual(len(data['frames'][0]['positions']), 3)
        self.assertFalse(data['overview']['include_goalkeepers'])
        status, _, body = self.request('/api/summary?team_id=0&start_s=0&end_s=0.08')
        summary = json.loads(body)
        self.assertEqual(summary['statistics']['width']['mean'], 40.)
        self.assertEqual(summary['available_ratio'], .5)
        self.assertEqual(summary['valid_player_count_range'], [2, 2])

    def test_video_ranges_support_seeking_and_invalid_ranges(self):
        status, headers, body = self.request('/media/video', headers={'Range': 'bytes=3-6'})
        self.assertEqual((status, body), (206, b'3456'))
        self.assertEqual(headers['Content-Range'], 'bytes 3-6/16')
        self.assertEqual(self.request('/media/video', headers={'Range': 'bytes=-3'})[2], b'def')
        self.assertEqual(self.request('/media/video', headers={'Range': 'bytes=99-'})[0], 416)
        self.assertEqual(self.request('/media/video', method='HEAD')[2], b'')

    def test_no_arbitrary_files_and_foreign_origins(self):
        for path in ('/.env', '/../.env', '/api/../../.ssh/id_rsa'):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request('/api/dataset', headers={'Host': 'untrusted.example'})[0], 403)
        self.assertEqual(self.request('/api/ask', 'POST', '{}', {'Content-Type': 'application/json',
                                                              'Origin': 'https://untrusted.example'})[0], 403)
        self.assertEqual(self.request('/api/summary?team_id=0&start_s=NaN&end_s=1')[0], 400)

    def test_model_result_is_saved_with_selection_and_evidence(self):
        result = {'answer': '真实测试回答 [E1]', 'evidence': [{'evidence_id': 'E1'}], 'note': '测试'}
        request = {'question': '宽度是多少？', 'team_id': 0, 'start_s': 0, 'end_s': .08}
        headers = {'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{self.port}'}
        with patch('examples.soccer.web.run_agent', return_value=result) as agent:
            status, _, body = self.request('/api/ask', 'POST', json.dumps(request), headers)
        self.assertEqual(status, 200)
        response = json.loads(body)
        self.assertEqual(response['selection']['team_id'], 0)
        self.assertIn('[0,0.08)秒', agent.call_args.args[0])
        saved = self.workspace.output/response['request_id']/'trace.json'
        self.assertTrue(saved.exists())
        self.assertEqual(json.loads(saved.read_text(encoding='utf-8')), response)
        self.assertEqual(self.request('/api/ask', 'POST', '[]', headers)[0], 400)

    def test_concurrent_paid_requests_are_not_duplicated(self):
        self.workspace.lock.acquire()
        try:
            with self.assertRaises(BlockingIOError):
                self.workspace.ask({'question': '宽度？', 'team_id': 0, 'start_s': 0, 'end_s': .08})
        finally:
            self.workspace.lock.release()

    def test_failed_model_call_saves_diagnostics_without_fake_answer(self):
        error = DeepSeekError('证据校验失败', evidence=[{'evidence_id': 'E1', 'success': True}],
                              validation=[{'issues': ['缺少知识引用']}])
        request = {'question': '查询宽度', 'team_id': 0, 'start_s': 0, 'end_s': .08}
        headers = {'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{self.port}'}
        with patch('examples.soccer.web.run_agent', side_effect=error):
            status, _, body = self.request('/api/ask', 'POST', json.dumps(request), headers)
        self.assertEqual(status, 502)
        self.assertNotIn('answer', json.loads(body))
        files = list(self.workspace.output.glob('*/failed-trace.json'))
        self.assertEqual(len(files), 1)
        saved = json.loads(files[0].read_text(encoding='utf-8'))
        self.assertEqual(saved['status'], 'failed')
        self.assertNotIn('answer', saved)


if __name__ == '__main__':
    unittest.main()
