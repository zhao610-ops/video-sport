"""只读取分析 JSON，生成轨迹和观测热区；不加载模型或原视频。"""

import argparse
import html
import json
from collections import Counter, defaultdict
from pathlib import Path


def render_report(input_path, output_path):
    with open(input_path, encoding='utf-8') as stream:
        data = json.load(stream)
    if data.get('schema_version') != '1.0':
        raise ValueError('不支持的数据格式版本')
    tracks = defaultdict(list)
    heat = Counter()
    total = valid = mapping_frames = 0
    for frame in data['frames']:
        mapping_frames += bool(frame['mapping']['valid'])
        for row in frame['positions']:
            total += 1
            if not row['coordinate_valid']:
                continue
            valid += 1
            tracks[row['track_id']].append(row)
            heat[min(19, int(row['x_norm'] / 5)), min(13, int(row['y_norm'] / (100 / 14)))] += 1
    colors = {0: '#e34b88', 1: '#168bbf', None: '#777777'}
    paths = []
    for track_id, rows in tracks.items():
        for left, right in zip(rows, rows[1:]):
            # 无效帧、漏检帧及编号间断处不连线，不假造运动轨迹。
            if right['frame_index'] != left['frame_index'] + 1:
                continue
            color = colors.get(right['team_id'], '#777777')
            paths.append(f'<line x1="{left["x_norm"] * 8:.2f}" y1="{left["y_norm"] * 5:.2f}" '
                         f'x2="{right["x_norm"] * 8:.2f}" y2="{right["y_norm"] * 5:.2f}" '
                         f'stroke="{color}" stroke-width="1.5"><title>跟踪编号 {track_id}</title></line>')
        last = rows[-1]
        paths.append(f'<circle cx="{last["x_norm"] * 8:.2f}" cy="{last["y_norm"] * 5:.2f}" '
                     f'r="3" fill="{colors.get(last["team_id"], "#777777")}"><title>跟踪编号 {track_id}</title></circle>')
    peak = max(heat.values(), default=1)
    cells = [f'<rect x="{x * 40}" y="{y * 500 / 14:.2f}" width="40" height="{500 / 14:.2f}" '
             f'fill="#f57c24" opacity="{count / peak:.3f}"><title>{count} 次有效观测</title></rect>'
             for (x, y), count in heat.items()]
    def pitch(content):
        return ('<svg viewBox="-8 -8 816 516" role="img"><rect width="800" height="500" fill="#edf5ec"/>'
                + content + '<g fill="none" stroke="#555"><rect width="800" height="500"/>'
                '<path d="M400 0V500"/><ellipse cx="400" cy="250" rx="60" ry="60"/></g></svg>')
    source = html.escape(data['metadata']['source_video'])
    document = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>足球站位数据检查</title><style>
body{{font-family:"Microsoft YaHei","微软雅黑",sans-serif;max-width:1050px;margin:32px auto;padding:0 20px;color:#24323c}}
svg{{width:100%;max-height:560px}} section{{border:1px solid #d6dfdf;border-radius:12px;padding:20px;margin:22px 0}}
p{{line-height:1.8}} code{{overflow-wrap:anywhere}}</style>
<h1>足球站位数据检查</h1><p>来源：<code>{source}</code></p>
<p>处理状态：{html.escape(data['summary']['status'])}；共 {len(data['frames'])} 帧，
{mapping_frames} 帧通过映射检查。共 {total} 条观测，其中 {valid} 条坐标有效。</p>
<p>坐标为球场长宽的 0～100，几何检查通过不代表真实位置已被测准。
未知尺寸仍依赖相对模板，模板偏差可能影响位置。示意图不表示实测球场比例。</p>
<section><h2>可见球员轨迹</h2><p>粉色、蓝色表示本次分析的两队，灰色表示球队未知。
仅连接连续有效帧；跟踪编号不是球衣号码，镜头切换后不保证身份连续。</p>{pitch(''.join(paths))}</section>
<section><h2>有效观测热区</h2><p>汇总球员与守门员的有效观测次数，颜色在本片段内归一化。
它受到镜头覆盖和漏检影响，不代表全场跑动强度或完整活动时间。</p>{pitch(''.join(cells))}</section>
<p>本页面由保存的数据生成，无需重新识别视频。尺寸状态：
{html.escape(data['metadata']['pitch_profile']['status'])}；本版不计算米制距离、速度。</p></html>'''
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding='utf-8')
    print(f'离线报告已生成：{output.resolve()}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='从已保存数据生成离线检查图')
    parser.add_argument('--input', required=True, help='analysis.json 路径')
    parser.add_argument('--output', required=True, help='输出 HTML 路径')
    args = parser.parse_args()
    render_report(args.input, args.output)
