"""本机战术分析工作台：读取已保存结果，连接现有统计、知识和智能体。"""

import argparse
import json
import math
import mimetypes
import re
import threading
import uuid
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from sports.annotators.pitch_svg import draw_pitch_svg
from sports.common.deepseek_agent import DeepSeekClient, DeepSeekError, load_local_env, run_agent
from sports.common.tactics import calculate_tactics
from sports.common.tactical_tools import TacticalTools
from sports.common.ball_data import load_ball_data


ROOT = Path(__file__).resolve().parents[2]


class Workspace:
    def __init__(self, analysis_path, video_path=None, env_file=None, output_dir=None, ball_path=None):
        with open(analysis_path, encoding='utf-8') as stream:
            self.analysis = json.load(stream)
        self.metrics = calculate_tactics(self.analysis, include_goalkeepers=False)
        self.tools = TacticalTools(self.metrics)
        self.video = Path(video_path or self.analysis['metadata']['source_video']).resolve()
        if not self.video.is_file():
            raise ValueError('找不到对应视频，请通过 --video 指定与分析结果匹配的原始视频')
        balls = load_ball_data(ball_path or Path(analysis_path).parent/'ball/ball.json',
                               analysis_path, self.video, self.analysis)
        balls_by_index = {row['frame_index']: row for row in balls['frames']}
        self.output = Path(output_dir or ROOT / 'outputs/web-agent')
        self.lock = threading.Lock()
        if env_file:
            load_local_env(env_file)
        try:
            self.client = DeepSeekClient(model='deepseek-flash')
        except DeepSeekError:
            self.client = None
        # 浏览器只接收显示需要的字段，不提供原始元数据或本机路径。
        frames = []
        for frame in self.analysis['frames']:
            positions = []
            if frame['mapping']['valid']:
                for point in frame['positions']:
                    if (point['coordinate_valid'] is True and type(point['track_id']) is int
                            and type(point['team_id']) is int and point['team_id'] in (0, 1)
                            and point['role'] in ('player', 'goalkeeper')
                            and all(type(point[key]) in (int, float) and math.isfinite(point[key])
                                    and 0 <= point[key] <= 100 for key in ('x_norm', 'y_norm'))):
                        positions.append({key: point[key] for key in
                                          ('track_id', 'team_id', 'role', 'x_norm', 'y_norm')})
            counts = Counter(point['track_id'] for point in positions)
            frames.append({'frame_index': frame['frame_index'], 'timestamp_s': frame['timestamp_s'],
                           'ball': balls_by_index.get(frame['frame_index']),
                           'mapping': {'valid': frame['mapping']['valid'], 'reason': frame['mapping']['reason']},
                           'positions': [point for point in positions if counts[point['track_id']] == 1]})
        self.dataset = {'overview': self.tools.overview(), 'fps': self.analysis['metadata']['fps'],
                        'frames': frames, 'team_frames': self.metrics['team_frames'],
                        'pitch_svg': draw_pitch_svg(self.analysis['metadata']['template_cm'], width=100, height=68),
                        'agent_ready': self.client is not None, 'model': 'deepseek-flash',
                        'video_url': '/media/video', 'video_name': self.video.name}
        self.dataset['ball'] = {key: value for key, value in balls.items() if key != 'frames'}

    def ask(self, request):
        if self.client is None:
            raise DeepSeekError('服务端未配置 DeepSeek 密钥；视频和统计仍可使用')
        if not isinstance(request, dict) or set(request) != {'question', 'team_id', 'start_s', 'end_s'}:
            raise ValueError('问答请求字段无效')
        question = request['question']
        if not isinstance(question, str) or not question.strip() or len(question) > 1000:
            raise ValueError('问题应为1到1000个字符')
        selected = self.tools.summarize(request['team_id'], request['start_s'], request['end_s'])
        if selected['extends_beyond_dataset'] or not selected['selected_frames']:
            raise ValueError('所选片段超出分析范围')
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError('已有分析问题正在处理，请等待完成后再发送')
        try:
            context = (f"当前网页选择球队{request['team_id']}，时间段"
                       f"[{request['start_s']},{request['end_s']})秒。请围绕该片段回答；"
                       f"如问题明确要求其他时间段，请按问题查询并说明。用户问题：{question}")
            try:
                result = run_agent(context, self.tools, self.client)
            except DeepSeekError as error:
                if error.evidence:
                    target = self.output / uuid.uuid4().hex
                    target.mkdir(parents=True)
                    with open(target / 'failed-trace.json', 'w', encoding='utf-8') as stream:
                        json.dump({'status': 'failed', 'evidence': error.evidence,
                                   'validation': error.validation}, stream, ensure_ascii=False,
                                  allow_nan=False, indent=2)
                raise
            identifier = uuid.uuid4().hex
            result.update(question=question, selection={key: request[key] for key in
                          ('team_id', 'start_s', 'end_s')}, model=self.client.model, request_id=identifier)
            target = self.output / identifier
            target.mkdir(parents=True)
            with open(target / 'trace.json', 'w', encoding='utf-8') as stream:
                json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
            (target / 'answer.md').write_text(result['answer'] + '\n', encoding='utf-8')
            return result
        finally:
            self.lock.release()


def make_handler(workspace):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'FootballWorkspace/1.0'

        def log_message(self, *_):
            # 不把问题、配置或请求头写入终端日志。
            pass

        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',
                                                f'localhost:{self.server.server_port}')

        def json_response(self, payload, status=200):
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def serve_file(self, path, video=False):
            if not path.is_file():
                self.json_response({'error': '文件不存在'}, 404)
                return
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            byte_range = self.headers.get('Range') if video else None
            if byte_range:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', byte_range)
                if match and any(match.groups()):
                    a, b = match.groups()
                    start, end = ((int(a), min(int(b), size-1) if b else size-1) if a
                                  else (max(0, size-int(b)), size-1))
                else:
                    start, end = size, -1
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                status = 206
            self.send_response(status)
            self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(end-start+1))
            self.send_header('X-Content-Type-Options', 'nosniff')
            if video:
                self.send_header('Accept-Ranges', 'bytes')
                if status == 206:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            else:
                self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if self.command != 'HEAD':
                try:
                    with open(path, 'rb') as stream:
                        stream.seek(start)
                        remaining = end-start+1
                        while remaining:
                            block = stream.read(min(remaining, 128*1024))
                            if not block:
                                break
                            self.wfile.write(block)
                            remaining -= len(block)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self.valid_host():
                self.json_response({'error': '仅允许本机工作台访问'}, 403)
                return
            path = urlsplit(self.path).path
            if path == '/api/dataset':
                self.json_response(workspace.dataset)
            elif path == '/api/knowledge':
                self.json_response(workspace.tools.knowledge.data)
            elif path == '/api/summary':
                try:
                    query = parse_qs(urlsplit(self.path).query)
                    result = workspace.tools.summarize(int(query['team_id'][0]),
                                                       float(query['start_s'][0]), float(query['end_s'][0]))
                    self.json_response(result)
                except (ValueError, KeyError, OverflowError):
                    self.json_response({'error': '球队或时间段参数无效'}, 400)
            elif path == '/media/video':
                self.serve_file(workspace.video, video=True)
            else:
                files = {'/': ROOT/'web/index.html', '/app.js': ROOT/'web/app.js',
                         '/ball.js': ROOT/'web/ball.js',
                         '/style.css': ROOT/'web/style.css', '/base.css': ROOT/'ui-prototype/style.css',
                         '/local-fonts/yahei.ttf': ROOT/'ui-prototype/local-fonts/yahei.ttf'}
                if path not in files:
                    self.json_response({'error': '地址不存在'}, 404)
                else:
                    self.serve_file(files[path])

        def do_POST(self):
            if not self.valid_host() or self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
                self.json_response({'error': '仅允许工作台页面提交请求'}, 403)
                return
            if self.path != '/api/ask':
                self.json_response({'error': '地址不存在'}, 404)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16000 or self.headers.get_content_type() != 'application/json':
                    raise ValueError('请求格式或大小无效')
                request = json.loads(self.rfile.read(length).decode('utf-8'))
                self.json_response(workspace.ask(request))
            except BlockingIOError as error:
                self.json_response({'error': str(error)}, 429)
            except (ValueError, UnicodeError):
                self.json_response({'error': '问题、球队或时间段无效'}, 400)
            except DeepSeekError as error:
                self.json_response({'error': str(error)}, 502)
            except OSError:
                self.json_response({'error': '回答保存失败，请检查服务端磁盘与权限'}, 500)
    return Handler


def main():
    parser = argparse.ArgumentParser(description='在本机浏览器查看真实足球分析结果并提问')
    parser.add_argument('--analysis', default=str(ROOT/'examples/soccer/data/validation-0bfacc-refined/analysis.json'))
    parser.add_argument('--video', help='与站位数据对应的原始视频路径')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--env-file', default=str(ROOT/'.env'))
    args = parser.parse_args()
    workspace = Workspace(args.analysis, args.video, args.env_file)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(workspace))
    print(f'真实分析工作台：http://127.0.0.1:{server.server_port}', flush=True)
    print('仅监听本机；从已保存坐标计算指标，不重新运行识别模型。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
