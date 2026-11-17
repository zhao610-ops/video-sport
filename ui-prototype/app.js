/* 纯静态交互原型：所有指标、站位与问答均为演示，不请求分析服务。 */
'use strict';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const svgNS = 'http://www.w3.org/2000/svg';
const state = { time: 5, team: 0, range: [5, 10], mode: 'positions', selected: null, busy: false };
const video = $('#match-video');
const dialog = $('#detail-dialog');
let objectURL = null;
let toastTimer;
const mockMetrics = {
  '0:0,5': { width: 64.7, span: 25.8, count: '10', quality: 42.4, frames: '53 / 125' },
  '0:5,10': { width: 65.8, span: 27.9, count: '9–10', quality: 94.4, frames: '118 / 125' },
  '0:0,10': { width: 65.5, span: 27.2, count: '9–10', quality: 68.4, frames: '171 / 250' },
  '1:0,5': { width: 58.2, span: 32.6, count: '8–10', quality: 44.0, frames: '55 / 125' },
  '1:5,10': { width: 59.6, span: 30.1, count: '9–10', quality: 87.2, frames: '109 / 125' },
  '1:0,10': { width: 59.1, span: 30.9, count: '8–10', quality: 65.6, frames: '164 / 250' },
};
const sources = {
  pressing: 'https://www.fifatrainingcentre.com/en/game/tournaments/fcwc/2025/team-analyses/increased-use-of-high-press-and-pressing-strategies.php',
  compactness: 'https://www.fifatrainingcentre.com/en/fwc2022/technical-and-tactical-analysis/controlling-the-game-without-the-ball--the-mid-block-and-compactness.php',
};
const knowledge = [
  ['K001', '高位逼抢', '在对手持球时于前场主动施压。判断需要球权、球位置、进攻方向与施压行为，站位靠前不是充分条件。', sources.pressing],
  ['K002', '中位防守与低位防守', '结合防守位置、组织形态与持续时间理解防守块。单帧球队中心不能确定防守阶段。', sources.compactness],
  ['K003', '紧凑性与阵型收缩', '关注队员及防线之间的空间连接。宽度和纵向跨度仅能描述整体形态，不能替代局部间距与防线层次。', sources.compactness],
  ['K004', '丢球反抢与防守转换', '丢球后迅速施压并封锁传球路线。需要明确球权转换时刻及其前后连续动作。', 'https://www.fifatrainingcentre.com/en/practice/elite-sessions/transition-to-defending/preparing-and-executing-counter-pressing.php'],
  ['K005', '进攻宽度与拉开空间', '横向展开有助于创造接应空间；效果取决于持球者、接应者和对手的关系。宽度增大不等于进攻质量提高。', 'https://www.fifatrainingcentre.com/en/game/game-analysis/in-possession/switch-of-play.php'],
  ['K006', '转移进攻', '通过改变球的进攻侧利用防守空间。球队中心横移不能代替球的跨侧移动证据。', 'https://www.fifatrainingcentre.com/en/game/game-analysis/in-possession/switch-of-play.php'],
  ['K007', '局部人数优势', '特定对抗区域中利用自由队员形成配合优势。画面中两队总人数差不代表球周围形成多打少。', 'https://www.fifatrainingcentre.com/en/practice/training-perspectives/designing-games-for-development/the-role-of-player-numbers-and-space.php'],
  ['K008', '项目指标定义', '中心为可见有效球员坐标的算术平均；宽度为 y 坐标极差，纵向跨度为 x 坐标极差。默认排除守门员。', null],
  ['K009', '事实与知识的边界', '战术知识提供一般判断条件，不能替代当前片段的事实证据。当前系统尚不能输出战术分类或比赛获胜概率。', null],
];
function stamp(time, fraction = false) {
  const value = Math.max(0, Math.min(10, time));
  return '00:' + String(Math.floor(value)).padStart(2, '0') + (fraction ? '.' + String(Math.round((value % 1) * 100) % 100).padStart(2, '0') : '');
}
function metrics() { return mockMetrics[`${state.team}:${state.range.join(',')}`]; }
function icon(name) { return `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`; }
function toast(text) {
  clearTimeout(toastTimer);
  $('#toast').textContent = text;
  $('#toast').hidden = false;
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 3600);
}
function showDialog(title, html, eyebrow = '分析依据') {
  $('#dialog-title').textContent = title;
  $('#dialog-eyebrow').textContent = eyebrow;
  $('#dialog-content').innerHTML = html;
  if (!dialog.open) dialog.showModal();
  dialog.scrollTop = 0;
}
function showEvidence(team = state.team, range = state.range.slice()) {
  const sample = mockMetrics[`${team}:${range.join(',')}`];
  showDialog('把结论与依据放在一起', `<p>当前演示：球队 ${team}，${stamp(range[0])}—${stamp(range[1])}。本弹窗演示未来的证据查看方式。</p>
    <div class="source-card"><small>演示数据 · 不是真实工具调用</small><strong>片段指标</strong>横向宽度 ${sample.width.toFixed(1)}%，纵向跨度 ${sample.span.toFixed(1)}%；可用帧 ${sample.frames}，可用率 ${sample.quality.toFixed(1)}%。数值不构成本视频的分析结论。</div>
    <div class="source-card"><small>K001 · FIFA Training Centre · 知识摘要</small><strong>高位逼抢</strong>判断需要球的位置、球权、攻防方向及球员施压动作，不能只看站位靠前。<br><a href="${sources.pressing}" target="_blank" rel="noopener">查看 FIFA 原始来源 ↗</a></div>
    <div class="source-card"><small>K003 · FIFA Training Centre · 知识摘要</small><strong>紧凑性</strong>整体展开范围不等于防线间距或局部空间连接。<br><a href="${sources.compactness}" target="_blank" rel="noopener">查看 FIFA 原始来源 ↗</a></div>
    <p>正式接入后，这里将展示实际工具请求、帧号、有效性与知识检索证据。当前原型不会调用 DeepSeek。</p>`);
}
function showLibrary() {
  showDialog('足球战术知识库', '<p>先理解概念，再检验片段是否满足判断条件。以下为现有 9 张知识卡片的界面摘要。</p><div class="knowledge-list">' + knowledge.map(([id, title]) => `<button data-card="${id}"><small>${id}</small>${title}</button>`).join('') + '</div>', '知识，让分析有据可依');
  $$('#dialog-content [data-card]').forEach(button => button.addEventListener('click', () => {
    const card = knowledge.find(item => item[0] === button.dataset.card);
    showDialog(card[1], `<p>${card[2]}</p><div class="source-card"><small>${card[0]} · ${card[3] ? '外部资料中文摘要与项目适用说明' : '本项目统计与分析口径'}</small><strong>来源与适用边界</strong>${card[3] ? `<a href="${card[3]}" target="_blank" rel="noopener">FIFA Training Centre 原始资料 ↗</a>` : '本项目指标定义与映射口径。'}<p>知识说明不证明当前视频中发生了这一战术。</p></div><button class="button secondary" id="back-library">返回知识目录</button>`, '足球战术知识库');
    $('#back-library').addEventListener('click', showLibrary);
  }));
}
function position(index, team, time) {
  const base = [[24, 12], [20, 27], [24, 42], [28, 57], [39, 7], [39, 23], [41, 42], [43, 59], [56, 24], [56, 46]][index];
  return { x: (team ? 100 - base[0] : base[0]) + Math.sin(time * .55 + index) * 2.8,
    y: base[1] + Math.cos(time * .43 + index * 1.3 + team) * 2.1 };
}
function drawPitch() {
  const layer = $('#player-layer');
  layer.replaceChildren();
  $('#trail-layer').replaceChildren();
  $('#heat-layer').replaceChildren();
  for (let team = 0; team < 2; team++) {
    for (let index = 0; index < 10; index++) {
      const point = position(index, team, state.time);
      const id = index + 1 + team * 10;
      const color = team ? '#df6b2c' : '#3675d2';
      if (state.mode === 'trails' && team === state.team) {
        const trail = document.createElementNS(svgNS, 'path');
        const points = Array.from({ length: 18 }, (_, n) => position(index, team, Math.max(0, state.time - 3 + n * 3 / 17)));
        trail.setAttribute('d', points.map((p, n) => `${n ? 'L' : 'M'}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' '));
        trail.setAttribute('stroke', color);
        trail.setAttribute('stroke-width', '.8');
        trail.setAttribute('opacity', '.55');
        $('#trail-layer').append(trail);
      }
      if (state.mode === 'heatmap' && team === state.team) {
        const heat = document.createElementNS(svgNS, 'circle');
        heat.setAttribute('cx', point.x);
        heat.setAttribute('cy', point.y);
        heat.setAttribute('r', '11');
        heat.setAttribute('fill', `url(#heat-${team ? 'orange' : 'blue'})`);
        $('#heat-layer').append(heat);
      }
      const group = document.createElementNS(svgNS, 'g');
      group.setAttribute('class', 'player-point');
      group.setAttribute('data-player', String(id));
      group.setAttribute('role', 'button');
      group.setAttribute('tabindex', '0');
      group.setAttribute('aria-label', `演示球队${team}，球员${id}，查看相对坐标`);
      group.innerHTML = `<circle cx="${point.x}" cy="${point.y}" r="${state.selected === id ? 2.2 : 1.8}" fill="${color}"/><text x="${point.x}" y="${point.y + .1}">${id}</text>`;
      const select = () => {
        const hadFocus = document.activeElement === group;
        video.pause(); state.selected = id; updatePlayerDetail(); drawPitch();
        if (hadFocus) layer.querySelector(`[data-player="${id}"]`).focus();
      };
      group.addEventListener('click', select);
      group.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(); } });
      layer.append(group);
    }
  }
  $('#pitch-time').textContent = stamp(state.time, true);
}
function updatePlayerDetail() {
  if (state.selected === null) return;
  const team = state.selected > 10 ? 1 : 0;
  const index = (state.selected - 1) % 10;
  const point = position(index, team, state.time);
  $('#player-detail').textContent = `球队 ${team} · #${state.selected}　x ${point.x.toFixed(1)}% / y ${(point.y / 68 * 100).toFixed(1)}%（模拟）`;
}
function chartValue(time) { return 62 + state.team * -5 + time * .52 + Math.sin(time * 1.7 + state.team) * 1.4; }
function drawChart() {
  const chart = $('#metric-chart');
  const points = Array.from({ length: 51 }, (_, index) => [26 + index / 50 * 608, 80 - (chartValue(index / 5) - 50) * 2.3]);
  const line = points.map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const cursor = 26 + state.time / 10 * 608;
  chart.innerHTML = `<defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#ed5148" stop-opacity=".12"/><stop offset="1" stop-color="#ed5148" stop-opacity="0"/></linearGradient></defs>
    <rect x="${26 + state.range[0] / 10 * 608}" y="8" width="${(state.range[1] - state.range[0]) / 10 * 608}" height="79" fill="#faf6f5" stroke="none"/>
    <g stroke="#eef0f3" stroke-dasharray="3 4"><path d="M26 18H634M26 51H634M26 84H634"/></g>
    <text x="0" y="21">80</text><text x="0" y="54">65</text><text x="0" y="87">50</text>
    <path d="${line}L634 86H26Z" fill="url(#chart-fill)" stroke="none"/><path d="${line}" stroke="#ed5148" stroke-width="2" fill="none"/>
    <path d="M${cursor} 8V86" stroke="#aaa5a3" stroke-dasharray="3 3"/><circle cx="${cursor}" cy="${80 - (chartValue(state.time) - 50) * 2.3}" r="3.2" fill="#ed5148" stroke="white" stroke-width="1.5"/>
    ${[0, 2, 4, 6, 8, 10].map(t => `<text x="${26 + t / 10 * 608}" y="106" text-anchor="middle">${stamp(t)}</text>`).join('')}`;
}
function updateMetrics() {
  const data = metrics();
  $('#width-value').innerHTML = `${data.width.toFixed(1)}<small>%</small>`;
  $('#span-value').innerHTML = `${data.span.toFixed(1)}<small>%</small>`;
  $('#count-value').innerHTML = `${data.count}<small> 人</small>`;
  $('#quality-value').innerHTML = `${data.quality.toFixed(1)}<small>%</small>`;
  $('#quality-frames').textContent = data.frames;
  $('#quality-bar').style.width = data.quality + '%';
  $('#current-team-caption').textContent = `正在查看球队 ${state.team}`;
  $('#context-time').textContent = `${stamp(state.range[0])} — ${stamp(state.range[1])}`;
  $('#range-highlight').style.left = state.range[0] * 10 + '%';
  $('#range-highlight').style.right = 100 - state.range[1] * 10 + '%';
  drawChart();
}
function setTime(time, seek = true) {
  state.time = Math.max(0, Math.min(10, time));
  if (seek && video.readyState > 0) video.currentTime = Math.min(state.time, Number.isFinite(video.duration) ? video.duration : state.time);
  $('#timeline').value = state.time;
  $('#play-time').textContent = stamp(state.time, true);
  $('#overlay-time').textContent = stamp(state.time, true);
  drawPitch();
  drawChart();
  updatePlayerDetail();
}
function playbackState() {
  const playing = !video.paused;
  $('#play-toggle').innerHTML = icon(playing ? 'pause' : 'play');
  $('#play-toggle').setAttribute('aria-label', playing ? '暂停片段' : '播放片段');
  $('#center-play').hidden = playing || !$('#video-fallback').hidden;
}
async function togglePlayback() {
  if (!video.paused) { video.pause(); return; }
  if (video.readyState === 0 || video.error) { toast('请先选择一段本地视频，或拖动时间轴体验模拟站位。'); return; }
  if (state.time >= 9.96) setTime(0);
  try { await video.play(); } catch { toast('视频无法播放，请选择浏览器支持的 MP4 视频。'); }
}
video.addEventListener('loadedmetadata', () => { $('#video-fallback').hidden = true; setTime(Math.min(state.time, video.duration || 10)); playbackState(); });
video.addEventListener('timeupdate', () => { if (video.currentTime >= 10) video.pause(); setTime(Math.min(video.currentTime, 10), false); });
video.addEventListener('play', playbackState);
video.addEventListener('pause', playbackState);
video.addEventListener('error', () => { $('#video-fallback').hidden = false; playbackState(); });
$('#play-toggle').addEventListener('click', togglePlayback);
$('#center-play').addEventListener('click', togglePlayback);
$('#timeline').addEventListener('input', event => { video.pause(); setTime(Number(event.target.value)); });
$('#speed').addEventListener('change', event => { video.playbackRate = Number(event.target.value); });
$('#expand-video').addEventListener('click', () => {
  const stage = $('#video-stage');
  if (stage.requestFullscreen) stage.requestFullscreen().catch(() => toast('当前环境不支持全屏，可以调整浏览器窗口查看。'));
  else toast('当前浏览器不支持全屏，请放大窗口查看。');
});
[$('#choose-video'), $('#fallback-select')].forEach(button => button.addEventListener('click', () => $('#video-file').click()));
$('#video-file').addEventListener('change', event => {
  const file = event.target.files[0];
  if (!file) return;
  video.pause();
  if (objectURL) URL.revokeObjectURL(objectURL);
  objectURL = URL.createObjectURL(file);
  state.time = 0;
  video.src = objectURL;
  video.load();
  toast('已选择本地视频；模拟指标与站位不会变成该视频的识别结果。');
});
$$('[data-team]').forEach(button => button.addEventListener('click', () => {
  state.team = Number(button.dataset.team);
  $$('[data-team]').forEach(item => { const selected = item === button; item.classList.toggle('selected', selected); item.setAttribute('aria-pressed', String(selected)); });
  updateMetrics(); drawPitch();
}));
$$('[data-range]').forEach(button => button.addEventListener('click', () => {
  state.range = button.dataset.range.split(',').map(Number);
  $$('[data-range]').forEach(item => item.classList.toggle('selected', item === button));
  video.pause(); setTime(state.range[0]); updateMetrics();
}));
$$('[data-mode]').forEach(button => button.addEventListener('click', () => {
  state.mode = button.dataset.mode;
  $$('[data-mode]').forEach(item => { item.classList.toggle('selected', item === button); item.setAttribute('aria-pressed', String(item === button)); });
  $('#pitch-caption').textContent = state.mode === 'heatmap' ? '演示热区仅表示模拟点的扩散，不是累计活动密度。' : state.mode === 'trails' ? '模拟最近 3 秒轨迹，仅用于预览交互效果。' : '站位为模拟点，不是本视频识别结果。';
  drawPitch();
}));
function addUserMessage(text) {
  const element = document.createElement('div');
  element.className = 'message user';
  const name = document.createElement('span'); name.className = 'speaker'; name.textContent = '你';
  const body = document.createElement('p'); body.textContent = text;
  element.append(name, body); $('#messages').append(element);
}
function answerDemo(question) {
  if (state.busy) return;
  const input = question.trim();
  if (!input) { $('#question').focus(); toast('请先输入一个针对片段的问题。'); return; }
  state.busy = true;
  const team = state.team, range = state.range.slice(), data = { ...metrics() };
  addUserMessage(input);
  $('#question').value = '';
  $('#chat-form button').disabled = true;
  const message = document.createElement('div'); message.className = 'message assistant';
  message.innerHTML = `<span class="speaker">${icon('spark')}战术助手 <span>演示回答</span></span><p>正在展示片段分析示例…</p>`;
  $('#messages').append(message); $('#messages').scrollTop = $('#messages').scrollHeight;
  setTimeout(() => {
    let explanation;
    if (/逼抢|压迫|胜率|预测/.test(input)) explanation = '这些指标不足以确定高位逼抢，更不能推出获胜概率。还需要球权、球坐标、进攻方向和连续施压行为等证据。';
    else if (/紧凑|收缩|阵型/.test(input)) explanation = '紧凑性还涉及队员及防线间的距离。当前只能描述可见球员的展开范围，不能仅凭两个跨度认定全队阵型更紧凑。';
    else explanation = '可先对照右侧站位，再查看宽度与纵向跨度。示例只演示回答如何引用依据，尚未对你的问题执行真实分析。';
    message.innerHTML = `<span class="speaker">${icon('spark')}战术助手 <span>演示回答</span></span><p>球队 ${team}，${stamp(range[0])}—${stamp(range[1])}：演示宽度均值 <strong>${data.width.toFixed(1)}%</strong>，纵向跨度 <strong>${data.span.toFixed(1)}%</strong>，可用率 ${data.quality.toFixed(1)}%。</p><p>${explanation}</p><button class="evidence-link">${icon('file')}查看本条示例依据${icon('arrow')}</button>`;
    message.querySelector('button').addEventListener('click', () => showEvidence(team, range));
    state.busy = false; $('#chat-form button').disabled = false; $('#messages').scrollTop = $('#messages').scrollHeight;
  }, 450);
}
$('#chat-form').addEventListener('submit', event => { event.preventDefault(); answerDemo($('#question').value); });
$('#question').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); answerDemo($('#question').value); } });
$$('[data-question]').forEach(button => button.addEventListener('click', () => answerDemo(button.dataset.question)));
$('#ask-range').addEventListener('click', () => answerDemo('这段时间球队的站位有什么特点？'));
$$('[data-evidence]').forEach(button => button.addEventListener('click', () => showEvidence()));
$('#data-details').addEventListener('click', () => showDialog('关于这份界面原型', '<p>本页面用于确认布局和交互。视频来自本机已有素材；球员站位、轨迹、热区、指标及聊天内容均为演示。</p><h3>本次可以体验</h3><p>播放视频、拖动时间轴、选择前后片段、切换球队、查看模拟坐标、展开知识与数据依据。</p><h3>正式数据接入后</h3><p>读取保存的逐帧分析结果，让视频、站位与指标真正对应；通过后端调用 DeepSeek，并保存可复核的工具证据。</p><h3>文件与隐私</h3><p>所选视频仅在本机浏览器读取，未上传任何服务器。原型不读取 API 密钥、不请求模型或分析服务。</p>', '当前状态 · 交互原型'));
$('#open-knowledge').addEventListener('click', showLibrary);
$$('[data-page]').forEach(button => button.addEventListener('click', () => {
  if (button.dataset.page === 'library') showLibrary();
  if (button.dataset.page === 'guide') showDialog('从画面到依据，四步完成分析', '<h3>1 · 选片段</h3><p>播放或拖动时间轴，选择前 5 秒、后 5 秒或完整片段。</p><h3>2 · 看站位</h3><p>切换球队与显示模式，点击或通过键盘选中球员标记。</p><h3>3 · 查数据</h3><p>查看片段均值及可用率。百分比描述空间跨度，不能当作米制距离。</p><h3>4 · 问助手</h3><p>针对片段提问，展开数据和知识依据。本次为固定演示回答，不调用真实模型。</p>', '使用说明');
  if (button.dataset.page === 'analysis') $('#workspace').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
}));
$('#close-dialog').addEventListener('click', () => dialog.close());
$('#close-dialog-bottom').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } });
document.addEventListener('visibilitychange', () => { if (document.hidden) video.pause(); });
updateMetrics(); setTime(5, false); playbackState();
