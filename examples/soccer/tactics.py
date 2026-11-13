"""读取站位数据，导出基础指标和带时间轴的离线报告。"""

import argparse
import csv
import html
import json
from pathlib import Path

from sports.annotators.pitch_svg import draw_pitch_svg
from sports.common.tactics import calculate_tactics


def render_tactics_report(data, output_path):
    rows = data['team_frames']
    indices = sorted({row['frame_index'] for row in rows})
    groups = {index: [] for index in indices}
    for row in rows:
        groups[row['frame_index']].append(row)
    samples = [groups[index] for index in indices]
    duration = max((row['timestamp_s'] for row in rows), default=1.) or 1.
    template = data['metadata']['template_cm']
    pitch_height = 100 * template['width'] / template['length']
    background = draw_pitch_svg(template, 100., pitch_height)
    colors = {0: '#d82c78', 1: '#087fae'}

    def chart(field, title, maximum=100., unit='百分比'):
        parts = [f'<h3>{title}</h3><svg viewBox="0 0 920 235" class="chart" role="img" aria-label="{title}">']
        for i in range(5):
            y = 190 - i * 40
            parts.append(f'<path d="M55 {y}H900" stroke="#dbe3e7"/>'
                         f'<text x="46" y="{y+5}" text-anchor="end">{i*maximum/4:g}</text>')
        for i in range(6):
            x = 55 + i * 169
            parts.append(f'<text x="{x}" y="218" text-anchor="middle">{duration*i/5:.1f}s</text>')
        for team in (0, 1):
            path = []
            isolated_starts = []
            previous = None
            for row in rows:
                if row['team_id'] != team:
                    continue
                value = row[field] if (row['available'] or
                                      field == 'visible_count' and row['reason'] != 'frame_mapping_invalid') else None
                if value is None:
                    previous = None
                    continue
                x = 55 + row['timestamp_s'] / duration * 845
                y = 190 - value / maximum * 160
                command = 'L' if previous is not None and row['frame_index'] == previous + 1 else 'M'
                path.append(f'{command}{x:.3f},{y:.3f}')
                if command == 'M':
                    isolated_starts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="2" fill="{colors[team]}">'
                                           f'<title>球队 {team}，{row["timestamp_s"]:.2f} 秒，{value:.2f}</title></circle>')
                previous = row['frame_index']
            parts.append(f'<path d="{" ".join(path)}" fill="none" stroke="{colors[team]}" stroke-width="2"/>')
            parts.extend(isolated_starts)
        parts.append('<path class="cursor" d="M55 25V195" stroke="#555" stroke-dasharray="4 4"/>'
                     f'<text x="55" y="17">{unit}</text></svg>')
        return ''.join(parts)

    charts = ''.join([
        chart('width', '横向宽度：占球场宽度的比例'),
        chart('longitudinal_span', '纵向跨度：占球场长度的比例'),
        chart('center_x', '球队中心 x：沿球场长度方向'),
        chart('center_y', '球队中心 y：沿球场宽度方向'),
        chart('visible_count', '参与统计的有效可见人数',
              max(12, max((row['visible_count'] for row in rows), default=0)), '人数'),
    ])
    metadata = data['metadata']
    scope = '包含守门员' if metadata['include_goalkeepers'] else '排除守门员'
    summary = data['summary']
    payload = json.dumps(samples, ensure_ascii=False, allow_nan=False).replace('</', '<\\/')
    document = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>可见球员战术指标</title>
<style>body{font-family:"Microsoft YaHei","微软雅黑",sans-serif;max-width:1120px;margin:28px auto;padding:0 20px;color:#233642;background:#f6f8fa}
p{line-height:1.8}section{background:white;border:1px solid #d8e1e6;border-radius:12px;padding:20px;margin:20px 0}
.current{display:grid;grid-template-columns:1fr 1fr;gap:20px}#pitch{width:100%}.chart{width:100%;height:235px}.chart text{font-size:13px}
#cards p{margin:6px 0}.team{padding:12px;margin-bottom:12px;border-left:4px solid #aaa;background:#f5f7f9}
input{width:100%}code{overflow-wrap:anywhere}@media(max-width:800px){.current{grid-template-columns:1fr}}
</style><h1>可见球员的基础战术指标</h1><p>来源：SOURCE_PLACEHOLDER</p>
<p>SCOPE_PLACEHOLDER；至少 MIN_PLACEHOLDER 名有效目标才输出指标。只有画面内的有效观测参与计算，不能代表完整阵型。
球场尺寸状态：PROFILE_PLACEHOLDER。球队 0/1 不代表主客队；球场 x 方向不代表进攻方向。</p>
<p>SUMMARY_PLACEHOLDER</p><section><h2>逐帧查看</h2><input id="slider" type="range" min="0" value="0"><p id="time"></p>
<div class="current"><svg id="pitch" role="img" aria-label="两队有效可见球员范围和中心"></svg><div id="cards"></div></div>
<p>粉色为球队 0，蓝色为球队 1。虚线框为可见球员的坐标范围，大圆点为算术平均中心。
无效帧和人数不足的帧不补点、不连线。人数为零可能是映射无效，不表示画面里没有球员。</p></section>
<section><h2>随时间变化</h2><p>纵轴均为相对坐标百分比或人数；空段表示该帧缺失。
极值跨度对误检测敏感，曲线变化也可能来自镜头覆盖、跟踪或球队分类变化，不能直接解释成战术变化。</p>CHARTS_PLACEHOLDER</section>
<script id="data" type="application/json">DATA_PLACEHOLDER</script><script>
const samples=JSON.parse(document.getElementById('data').textContent);
const background=BACKGROUND_PLACEHOLDER, H=HEIGHT_PLACEHOLDER, duration=DURATION_PLACEHOLDER;
const slider=document.getElementById('slider');slider.max=Math.max(0,samples.length-1);slider.disabled=!samples.length;
slider.value=Math.max(0,samples.findIndex(rows=>rows.some(row=>row.available)));
const format=x=>x===null?'缺失':x.toFixed(2)+'%';
function draw(){if(!samples.length){document.getElementById('time').textContent='没有可展示的数据';return;}
const rows=samples[Number(slider.value)], timestamp=rows[0].timestamp_s;let shapes='';let cards='';
for(const row of rows){const color=row.team_id===0?'#d82c78':'#087fae';
const reason={frame_mapping_invalid:'本帧映射无效',insufficient_players:'有效人数不足',player_count_exceeds_limit:'人数超过角色上限，需检查误检或球队分类'};
cards+=`<div class="team" style="border-color:${color}"><strong>球队 ${row.team_id}</strong><p>有效候选人数：${row.visible_count}（其中守门员 ${row.goalkeeper_count}）</p><p>${row.available?'有可计算数据':'缺失：'+reason[row.reason]}</p><p>中心：x ${format(row.center_x)} / y ${format(row.center_y)}</p><p>横向宽度：${format(row.width)}</p><p>纵向跨度：${format(row.longitudinal_span)}</p></div>`;
if(row.available){shapes+=`<rect x="${row.min_x}" y="${row.min_y*H/100}" width="${row.max_x-row.min_x}" height="${(row.max_y-row.min_y)*H/100}" fill="${color}" fill-opacity=".05" stroke="${color}" stroke-width=".4" stroke-dasharray="1 1"/><circle cx="${row.center_x}" cy="${row.center_y*H/100}" r="1.5" fill="${color}" stroke="white" stroke-width=".3"><title>球队 ${row.team_id} 中心</title></circle>`;}}
const pitch=document.getElementById('pitch');pitch.setAttribute('viewBox',`-5 -5 110 ${H+10}`);pitch.innerHTML=background+shapes;
document.getElementById('cards').innerHTML=cards;document.getElementById('time').textContent=`第 ${rows[0].frame_index} 帧，视频 ${timestamp.toFixed(2)} 秒`;
document.querySelectorAll('.cursor').forEach(node=>node.setAttribute('d',`M${55+timestamp/duration*845} 25V195`));}
slider.oninput=draw;draw();
</script></html>'''
    replacements = {
        'SOURCE_PLACEHOLDER': '<code>' + html.escape(metadata['source_video']) + '</code>',
        'SCOPE_PLACEHOLDER': scope, 'MIN_PLACEHOLDER': str(metadata['min_players']),
        'PROFILE_PLACEHOLDER': html.escape(metadata['pitch_profile']['status']),
        'SUMMARY_PLACEHOLDER': f"共 {summary['frame_count']} 帧、{summary['team_frame_count']} 条球队逐帧记录，"
                               f"其中 {summary['available_team_frames']} 条有可计算指标；几何通过不代表真实定位已被测准。",
        'CHARTS_PLACEHOLDER': charts, 'DATA_PLACEHOLDER': payload,
        'BACKGROUND_PLACEHOLDER': json.dumps(background, ensure_ascii=False),
        'HEIGHT_PLACEHOLDER': str(pitch_height), 'DURATION_PLACEHOLDER': str(duration),
    }
    for key, value in replacements.items():
        document = document.replace(key, value)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding='utf-8')


def export_tactics(input_path, output_dir, include_goalkeepers, min_players=2):
    with open(input_path, encoding='utf-8') as stream:
        analysis = json.load(stream)
    result = calculate_tactics(analysis, include_goalkeepers, min_players)
    result['metadata']['source_analysis'] = str(Path(input_path).resolve())
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if any((output / name).exists() for name in ('metrics.json', 'metrics.csv', 'report.html')):
        raise FileExistsError('指标结果已存在，请选择新的输出目录')
    with open(output / 'metrics.json', 'w', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
    fields = ['frame_index', 'timestamp_s', 'team_id', 'visible_count', 'goalkeeper_count',
              'available', 'reason', 'center_x', 'center_y', 'width', 'longitudinal_span',
              'min_x', 'max_x', 'min_y', 'max_y', 'track_ids']
    with open(output / 'metrics.csv', 'w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in result['team_frames']:
            writer.writerow(dict(row, track_ids=json.dumps(row['track_ids'])))
    render_tactics_report(result, output / 'report.html')
    print(f'战术指标已生成：{output.resolve()}')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='不运行识别模型，计算可见球员的中心与跨度')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--goalkeepers', choices=['include', 'exclude'], default='exclude',
                        help='默认 exclude 排除守门员，include 可临时将其纳入统计')
    parser.add_argument('--min-players', type=int, default=2, help='至少 2，计算门槛不是完整阵型可靠性门槛')
    args = parser.parse_args()
    export_tactics(args.input, args.output_dir, args.goalkeepers == 'include', args.min_players)
