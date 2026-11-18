/* 足球显示仅使用当前帧实际检测；二维球场坐标明确标为地面投影。 */
'use strict';
let showBall = true;

function setupBallUI() {
  const panel = document.createElement('section');
  panel.className = 'card ball-card';
  panel.innerHTML = `<div class="section-head"><h2>足球检测与轨迹</h2><label class="ball-toggle"><input type="checkbox" id="ball-toggle" checked>显示</label></div>
    <div id="ball-state" role="status">正在读取足球数据…</div>
    <div class="quality-row"><span>当前帧置信度</span><strong id="ball-confidence">—</strong></div>
    <div class="quality-row"><span>画面坐标</span><strong id="ball-image-position">—</strong></div>
    <div class="quality-row"><span>球场地面投影</span><strong id="ball-projection">—</strong></div>
    <p id="ball-summary" class="ball-summary"></p>
    <p class="ball-warning">球场点为地面近似投影，未判断球是否腾空；不代表真实落地点。</p>`;
  $('.right-column').insertBefore(panel, $('.quality-card'));
  const overlay = document.createElementNS(NS, 'svg');
  overlay.id = 'ball-video-overlay';
  overlay.setAttribute('aria-label', '足球真实图像检测与最近两秒轨迹');
  const size = state.data.ball.image_size;
  if (size) {
    overlay.setAttribute('viewBox', `0 0 ${size.width} ${size.height}`);
    $('#video-stage').style.aspectRatio = `${size.width}/${size.height}`;
  }
  video.insertAdjacentElement('afterend', overlay);
  const ground = document.createElementNS(NS, 'g');
  ground.id = 'ball-ground-layer';
  $('#pitch').append(ground);
  $('#ball-toggle').addEventListener('change', event => {
    showBall = event.target.checked;
    drawBall();
  });
  if (!state.data.ball.available) {
    $('#ball-toggle').disabled = true;
  }
}

function ballPath(frames, projection) {
  let path = '', last = null;
  for (const frame of frames) {
    const ball = frame.ball;
    if (!ball?.detected || projection && !ball.projection_valid) { last = null; continue; }
    const x = projection ? ball.x_norm : ball.image_x;
    const y = projection ? ball.y_norm*.68 : ball.image_y;
    const connected = last && last.frame_index+1 === ball.frame_index && last.segment_id === ball.segment_id;
    path += `${connected ? 'L' : 'M'}${x},${y} `;
    last = ball;
  }
  return path;
}

function drawBall() {
  const imageLayer = $('#ball-video-overlay'), ground = $('#ball-ground-layer');
  if (!imageLayer || !ground) return;
  imageLayer.replaceChildren();
  ground.replaceChildren();
  const data = state.data.ball;
  if (!data.available) {
    $('#ball-state').textContent = data.reason;
    $('#ball-summary').textContent = '球员站位仍可使用；不会显示模拟足球。';
    return;
  }
  const frame = currentFrame(), ball = frame.ball;
  const detected = ball?.detected === true;
  $('#ball-state').textContent = detected ? `第 ${frame.frame_index} 帧 · 已检测 · 轨迹段 ${ball.segment_id}` :
    ball?.tracking_status === 'association_rejected' ? `第 ${frame.frame_index} 帧 · 候选未通过关联，不补位置` : `第 ${frame.frame_index} 帧 · 未检出，不补位置`;
  $('#ball-state').classList.toggle('missing', !detected);
  $('#ball-confidence').textContent = detected ? `${(ball.confidence*100).toFixed(1)}%` : '—';
  $('#ball-image-position').textContent = detected ? `${ball.image_x.toFixed(1)}, ${ball.image_y.toFixed(1)} px` : '—';
  $('#ball-projection').textContent = ball?.projection_valid ? `${ball.x_norm.toFixed(1)}%, ${ball.y_norm.toFixed(1)}%（近似）` :
    detected ? ball.projection_reason === 'out_of_bounds' ? '越界，暂不显示' : '映射无效，暂不显示' : '无观测';
  $('#ball-summary').textContent = `全片 ${data.summary.frames} 帧，${data.summary.detected_frames} 帧有检测；检出比例不是准确率。黄色线为最近 2 秒图像轨迹，黑色虚线为地面投影轨迹。`;
  if (!showBall) return;
  const history = state.data.frames.filter(f => f.timestamp_s >= Math.max(state.range[0], state.time-2)
    && f.frame_index <= frame.frame_index);
  imageLayer.append(pointNode('path', {d: ballPath(history, false), fill:'none', stroke:'#fff061',
    'stroke-width':3, 'stroke-linecap':'round', opacity:'.85'}));
  ground.append(pointNode('path', {d: ballPath(history, true), fill:'none', stroke:'#28312e',
    'stroke-width':'.6', 'stroke-dasharray':'1 1', opacity:'.8'}));
  if (detected) {
    const [x1, y1, x2, y2] = ball.bbox_xyxy;
    imageLayer.append(pointNode('rect', {x:x1-5, y:y1-5, width:x2-x1+10, height:y2-y1+10,
      fill:'none', stroke:'#fff061', 'stroke-width':2}));
    imageLayer.append(pointNode('circle', {cx:ball.image_x, cy:ball.image_y, r:13,
      fill:'none', stroke:'#fff061', 'stroke-width':2}));
  }
  if (ball?.projection_valid) {
    const x=ball.x_norm, y=ball.y_norm*.68;
    ground.append(pointNode('circle', {cx:x, cy:y, r:1.7, fill:'white', stroke:'#202b25', 'stroke-width':'.5'}));
    ground.append(pointNode('circle', {cx:x, cy:y, r:.55, fill:'#202b25', stroke:'none'}));
    const title = pointNode('title', {});
    title.textContent = '足球中心的地面近似投影，未验证是否贴地';
    ground.append(title);
  }
}
