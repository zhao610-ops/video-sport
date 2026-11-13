"""读取保存的数据和原视频，生成同一帧的离线人工核对页面。"""

import argparse
import base64
import html
import json
from pathlib import Path

import cv2


def build_review(input_path, output_path, sample_count=15, frame_indices=None):
    if frame_indices is None and sample_count < 2:
        raise ValueError('至少选择 2 帧')
    with open(input_path, encoding='utf-8') as stream:
        data = json.load(stream)
    frames = data['frames']
    if not frames:
        raise ValueError('没有可核对的数据帧')
    if frame_indices is None:
        selected = sorted({round(i * (len(frames) - 1) / (sample_count - 1))
                           for i in range(sample_count)})
    else:
        lookup = {frame['frame_index']: i for i, frame in enumerate(frames)}
        if not frame_indices or any(index not in lookup for index in frame_indices):
            raise ValueError('指定帧不在分析结果中')
        selected = [lookup[index] for index in sorted(set(frame_indices))]
    capture = cv2.VideoCapture(data['metadata']['source_video'])
    samples = []
    try:
        for index in selected:
            frame = frames[index]
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame['frame_index'])
            ok, image = capture.read()
            if not ok:
                raise ValueError(f'无法读取原视频第 {frame["frame_index"]} 帧')
            height, width = image.shape[:2]
            image = cv2.resize(image, (960, round(height * 960 / width)))
            ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                raise ValueError('抽帧编码失败')
            samples.append({**frame, 'image_width': width, 'image_height': height,
                            'image': 'data:image/jpeg;base64,' + base64.b64encode(encoded).decode('ascii')})
    finally:
        capture.release()
    payload = json.dumps(samples, ensure_ascii=False, allow_nan=False).replace('</', '<\\/')
    source = html.escape(data['metadata']['source_video'])
    template = data['metadata'].get('template_cm', {'width': 6250, 'length': 10000})
    display_height = 100 * template['width'] / template['length']
    document = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>逐帧坐标核对</title>
<style>body{font-family:"Microsoft YaHei","微软雅黑",sans-serif;margin:24px;color:#24323c;background:#f7f9fa}
h1{font-size:26px}p{line-height:1.8}button,input{font:inherit}button{padding:8px 18px;margin-right:12px}
.panes{display:grid;grid-template-columns:1fr 1fr;gap:18px}.pane{background:white;padding:16px;border:1px solid #d6dfdf;border-radius:12px}
svg{width:100%;display:block}input{width:65%;vertical-align:middle}#status{background:#eaf0f4;padding:12px}
code{overflow-wrap:anywhere}.selected{stroke:#151515;stroke-width:4}
@media(max-width:900px){.panes{grid-template-columns:1fr}}</style>
<h1>同一帧：原画面与二维站位</h1><p>来源：<code>SOURCE_PLACEHOLDER</code></p>
<p>拖动选择抽查帧；两侧编号一致，点击一个编号可同时突出对应目标。
粉色/蓝色表示本次聚类球队，灰色表示球队未知。左图叉号表示坐标无效；右图只显示有效点。</p>
<button id="prev">上个抽查点</button><input id="slider" type="range" min="0" value="0"><button id="next">下个抽查点</button>
<p id="status"></p><div class="panes"><div class="pane"><h2>原画面与落脚点</h2><svg id="source"></svg></div>
<div class="pane"><h2>同一时刻的相对站位</h2><svg id="pitch"></svg></div></div>
<p>请检查：靠近中线/边线的球员是否映射到对应区域；画面内球员有无明显错位。
本页面用于人工初查，不自动认定参数合格。几何通过不表示真实位置已测准，球场尺寸未知时仍依赖相对模板。</p>
<script id="samples" type="application/json">DATA_PLACEHOLDER</script><script>
const samples=JSON.parse(document.getElementById('samples').textContent);
const displayHeight=HEIGHT_PLACEHOLDER;
const slider=document.getElementById('slider');slider.max=samples.length-1;let selected=null;
const color=r=>r.team_id===0?'#ff4794':r.team_id===1?'#00bfff':'#999';
const marker=(r,x,y,size)=>{
const active=r.track_id===selected;
return `<g data-id="${r.track_id}" style="cursor:pointer"><circle cx="${x}" cy="${y}" r="${size}" fill="${color(r)}" stroke="${active?'#111':'white'}" stroke-width="${active?size*.65:size*.2}"/>
<text x="${x+size*1.3}" y="${y}" font-size="${size*2.2}" fill="${color(r)}" stroke="#111" stroke-width="${size*.15}" paint-order="stroke">${r.track_id}</text></g>`;};
function draw(){const frame=samples[Number(slider.value)];const source=document.getElementById('source');
source.setAttribute('viewBox',`0 0 ${frame.image_width} ${frame.image_height}`);
source.innerHTML=`<image href="${frame.image}" width="${frame.image_width}" height="${frame.image_height}"/>`+
frame.positions.map(r=>marker(r,r.image_x,r.image_y,6)+(r.coordinate_valid?'':`<text x="${r.image_x-16}" y="${r.image_y-12}" fill="red" font-size="28">×</text>`)).join('');
const background=`<rect width="100" height="${displayHeight}" fill="#e8f1e6" stroke="#555" stroke-width=".4"/><path d="M50 0V${displayHeight}" stroke="#555" stroke-width=".4"/><circle cx="50" cy="${displayHeight/2}" r="7.6" fill="none" stroke="#555" stroke-width=".4"/>`;
const pitch=document.getElementById('pitch');pitch.setAttribute('viewBox',`-5 -5 110 ${displayHeight+10}`);
pitch.innerHTML=background+frame.positions.filter(r=>r.coordinate_valid).map(r=>marker(r,r.x_norm,r.y_norm*displayHeight/100,.9)).join('');
const q=frame.mapping;document.getElementById('status').textContent=`第 ${frame.frame_index} 帧｜视频 ${frame.timestamp_s.toFixed(2)} 秒｜映射：${q.valid?'通过几何检查':'无效'}（${q.reason}）｜有效观测 ${frame.positions.filter(r=>r.coordinate_valid).length}/${frame.positions.length}｜内点 ${q.inliers??0}/${q.selected_keypoints??0}`;
document.querySelectorAll('[data-id]').forEach(node=>node.onclick=()=>{selected=Number(node.dataset.id);draw();});}
slider.oninput=draw;document.getElementById('prev').onclick=()=>{slider.value=Math.max(0,Number(slider.value)-1);draw();};
document.getElementById('next').onclick=()=>{slider.value=Math.min(samples.length-1,Number(slider.value)+1);draw();};draw();
</script></html>'''
    document = (document.replace('SOURCE_PLACEHOLDER', source)
                .replace('HEIGHT_PLACEHOLDER', str(display_height)).replace('DATA_PLACEHOLDER', payload))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding='utf-8')
    print(f'逐帧核对页已生成：{output.resolve()}，共 {len(samples)} 个抽查帧')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='不运行模型，生成原画面与站位对照')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--samples', type=int, default=15)
    parser.add_argument('--frames', type=int, nargs='+', help='指定需核对的原视频帧编号，优先于均匀抽帧')
    args = parser.parse_args()
    build_review(args.input, args.output, args.samples, args.frames)
