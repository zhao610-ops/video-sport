# 基于深度学习与智能体的足球战术分析系统的设计与实现

本仓库是计算机科学与技术专业本科毕业设计项目，目标是从**足球比赛电视转播视频**中提取可核查的战术数据，并由智能体基于这些数据提供战术问答与解释。

> 当前状态：**已实现映射质量检查、站位导出、离线轨迹/热区和基础可见球员指标。** 基于 [Roboflow Sports](https://github.com/roboflow/sports) 开发；比赛检索、智能体和完整界面仍待实现。以下“规划功能”不代表已经完成。

## 项目目标与处理流程

```text
电视转播视频
  → 球员、守门员、裁判与足球检测
  → 多目标跟踪、球队分类
  → 球场关键点识别与坐标映射
  → 轨迹和战术数据提取
  → 战术可视化
  → 智能体调用数据分析工具，生成有依据的战术解释
```

本项目以赛后、离线分析为主要场景，先处理较短的比赛片段，再逐步扩展。电视转播画面会发生镜头切换，且常有球员不在画面内，因此系统应区分“观测到的数据”和“无法可靠判断的信息”，不把局部画面推断成完整的全场事实。

## 平台目标

项目以 **Windows 与 macOS 均可从源码安装、处理视频并查看输出** 为目标；不要求两台机器具有相同的处理速度，也暂不提供 `.exe` 或 `.app` 安装包。当前已加入跨平台资源准备脚本、自动设备选择和无预览窗口模式，但**尚未在 Windows 实机完成端到端验证**。平台适配只有在两种系统上运行相同测试视频后才能视为通过。

| 环境 | 首选推理设备 | 回退设备 |
| --- | --- | --- |
| Windows + NVIDIA 显卡 | CUDA | CPU |
| Apple 芯片 Mac | MPS（可用时） | CPU |
| 其他 Windows/Mac | CPU | — |

使用 `--device auto` 时程序按 CUDA → MPS → CPU 的顺序选择。Windows 端的 RTX 5060 Ti 需要安装与显卡兼容的 PyTorch CUDA 构建；具体命令请以 [PyTorch 官方安装选择器](https://pytorch.org/get-started/locally/)为准，不要照搬其他机器的安装命令。

## 当前基线能够做什么

`examples/soccer/main.py` 提供六种独立运行模式：

| 模式 | 当前功能 |
| --- | --- |
| `PITCH_DETECTION` | 识别球场关键点 |
| `PLAYER_DETECTION` | 检测球员、守门员、裁判和足球 |
| `BALL_DETECTION` | 检测并显示足球位置 |
| `PLAYER_TRACKING` | 给画面中的目标分配跟踪编号 |
| `TEAM_CLASSIFICATION` | 根据球衣视觉特征区分球队 |
| `RADAR` | 将可见球员映射到二维球场示意图 |

这些功能来自上游项目，并不等同于已经完成战术分析。当前也**没有**可直接用于智能体问答的完整、稳定的战术数据接口。

## 毕设计划实现的部分

1. **视觉基线复现与评估**：在选定的电视转播片段上运行检测、跟踪、球队分类和球场映射，记录失败场景与基线结果。
2. **关键环节改进**：针对镜头切换、遮挡或球场映射不稳定等问题，选择范围可控的算法改进点，开展消融或对比实验。
3. **战术数据提取**：从可靠的轨迹与球场坐标中计算热力图、球队站位、宽度与紧凑度等基础指标；进攻/防守阶段和基础战术模式识别作为后续扩展。
4. **智能体分析**：将战术指标封装为可调用的数据工具，使智能体按问题检索数据、解释结果、标注依据，并在数据不足时明确说明限制。
5. **可视化与系统集成**：展示处理视频、二维球场、指标图表及智能体问答结果，并完成实验评估与论文撰写。

以上是实施规划，实际完成情况将随开发进展更新，不预先承诺能够从单路转播视频准确恢复全场所有球员的位置或预测比赛结果。

## 目录说明

```text
.
├── examples/soccer/       # 足球示例、跨平台资源准备脚本和训练笔记本
├── sports/                # 上游通用运动视觉处理模块
├── README_UPSTREAM.md     # 保留的 Roboflow 原项目首页说明
├── LICENSE                # 上游 MIT 许可证
└── setup.py               # 上游 Python 包配置
```

## 运行现有足球示例

建议两台机器都使用 **Python 3.11** 和各自独立的虚拟环境。先按 [PyTorch 官方安装选择器](https://pytorch.org/get-started/locally/)在虚拟环境中安装适合本机的 PyTorch：Windows RTX 5060 Ti 选择可支持该显卡的 CUDA 构建；Apple 芯片 Mac 使用 macOS 安装方案。复制官网命令时，把命令开头的 `pip` 或 `pip3` 替换为下方对应平台的虚拟环境 Python 加 `-m pip`，确保安装到本项目环境中。然后安装本项目依赖。不要把一台机器的虚拟环境目录复制到另一台。

以下命令均从仓库根目录执行。macOS 终端：

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
# 此处先按 PyTorch 官网命令安装适合本机的 PyTorch
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m pip install -r examples/soccer/requirements.txt
```

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
# 此处先按 PyTorch 官网命令安装适合 RTX 5060 Ti 的 PyTorch CUDA 构建
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install -r examples/soccer/requirements.txt
```

足球示例的三个模型权重和示例视频不包含在仓库中。新脚本 `prepare_assets.py` 可在两个平台运行；默认只下载模型，添加 `--include-samples` 才下载上游示例视频。下载前请确认网络、文件来源、下载量和数据使用许可。原有的 `setup.sh` 是上游 Bash 脚本，Windows 用户无需运行它。

如果脚本无法连接 Google Drive，可从上游公开链接手动下载，并按下表文件名放到 `examples/soccer/data/`：

| 文件名 | 上游模型链接 |
| --- | --- |
| `football-ball-detection.pt` | [足球检测模型](https://drive.google.com/file/d/1isw4wx-MK9h9LMr36VvIWlJD6ppUvw7V/view) |
| `football-player-detection.pt` | [球员检测模型](https://drive.google.com/file/d/17PXFNlx-jI7VjVo_vQnB1sONjRyvoB-q/view) |
| `football-pitch-detection.pt` | [球场关键点模型](https://drive.google.com/file/d/1Ma5Kt86tgpdjCTKfum79YMgNnSjcoOyf/view) |

`RADAR` 和 `TEAM_CLASSIFICATION` 模式还会在首次运行时从 Hugging Face 获取 [SigLIP 特征模型](https://huggingface.co/google/siglip-base-patch16-224)；因此，即使三个 `.pt` 文件已备齐，完整雷达图仍需要能访问该模型或提前缓存它。先验证 `PLAYER_DETECTION` 模式可以把问题分开排查。

本机测试将 SigLIP 缓存保存在仓库的 `.cache/huggingface/`（不会提交到 Git）。复用这份缓存时，macOS 在运行命令前执行 `export HF_HOME="$PWD/.cache/huggingface"`；Windows PowerShell 执行 `$env:HF_HOME = "$PWD/.cache/huggingface"`。缓存下载完整后，可以设置 `HF_HUB_OFFLINE=1` 离线运行；换一台机器仍需单独准备缓存。下载后的球场、足球模型即使带有 `-v9`、`-v2` 后缀，也要重命名为表格中的固定文件名。

macOS：

```bash
./.venv/bin/python examples/soccer/prepare_assets.py --include-samples
./.venv/bin/python -m examples.soccer.main \
  --source_video_path examples/soccer/data/2e57b9_0.mp4 \
  --target_video_path examples/soccer/data/2e57b9_0-radar.mp4 \
  --device auto --mode RADAR --no-preview
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe examples/soccer/prepare_assets.py --include-samples
.\.venv\Scripts\python.exe -m examples.soccer.main `
  --source_video_path examples/soccer/data/2e57b9_0.mp4 `
  --target_video_path examples/soccer/data/2e57b9_0-radar.mp4 `
  --device auto --mode RADAR --no-preview
```

`--no-preview` 只保存结果视频，不打开 OpenCV 窗口；去掉即可边处理边预览。程序会打印实际选择的设备。若要处理自己的视频，将 `--source_video_path` 换成视频路径即可；带空格的路径需要加引号。更多基线模式见 [足球示例 README](examples/soccer/README.md)。

请从仓库根目录使用 `python -m examples.soccer.main` 启动；直接执行 `examples/soccer/main.py` 时，部分 Python 环境可能无法找到根目录下的 `sports` 包。

只有球员检测模型和示例视频时，可以先在 macOS 上依次验证检测与跟踪：

```bash
./.venv/bin/python -m examples.soccer.main \
  --source_video_path examples/soccer/data/2e57b9_0.mp4 \
  --target_video_path examples/soccer/data/2e57b9_0-player-detection.mp4 \
  --device auto --mode PLAYER_DETECTION --no-preview
./.venv/bin/python -m examples.soccer.main \
  --source_video_path examples/soccer/data/2e57b9_0.mp4 \
  --target_video_path examples/soccer/data/2e57b9_0-player-tracking.mp4 \
  --device auto --mode PLAYER_TRACKING --no-preview
```

2026 年 10 月 26 日在 Apple 芯片 Mac 上使用 MPS 完整处理了 30 秒示例视频，两个输出均为 750 帧、25 帧/秒。`setup.py` 将 `supervision` 固定为 0.30.9，因为上游跟踪代码使用的 `sv.ByteTrack` 已在 0.31 中移除。

### 双平台验收

2026 年 11 月 12 日 macOS MPS 基线验证结果：

| 模式 | 验证范围 | 输出文件（位于 `examples/soccer/data/`） |
| --- | --- | --- |
| 球场关键点检测 | 完整 30 秒，750 帧 | `2e57b9_0-pitch-detection.mp4` |
| 足球切片检测 | 前 2 秒，50 帧 | `2e57b9_0-ball-detection-preview.mp4` |
| 球队区分、跟踪与雷达图 | 完整 30 秒，750 帧；首、中、尾帧可读 | `2e57b9_0-radar.mp4` |

本次修复了 Supervision 0.30.9 的切片检测参数名，以及跟踪器启动时空结果导致的编号读取异常。雷达图模式已包含球队区分，但未单独运行完整的 `TEAM_CLASSIFICATION` 视频。上游雷达图不包含专用足球模型的检测结果。

这些结果确认了流程可运行，尚未评估检测准确率、身份切换率和映射位置误差。抽样雷达图中仍可见部分球员映射点越界；后续需要加入关键点置信度筛选、映射质量检查，并导出带时间戳、跟踪编号、球队与有效性标记的坐标数据，再开展战术统计。Windows 尚未完成验证。

使用同一段短视频，分别记录 Windows 和 macOS 上的 Python/PyTorch 版本、显卡与实际推理设备，并确认：依赖安装成功、三个模型可读取、`RADAR` 能处理完整片段、输出视频可播放。遇到模型不支持 GPU 或显存不足时，先用 `--device cpu` 排查功能问题，再处理加速兼容问题。

安装 PyTorch 后可先做设备检查。Windows PowerShell（预期 CUDA 为 `True`，且能在 CUDA 上创建张量）：

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available()); print(torch.ones(1, device='cuda'))"
```

Apple 芯片 Mac（预期 MPS 为 `True`）：

```bash
./.venv/bin/python -c "import torch; print(torch.__version__, torch.backends.mps.is_available())"
```

## 导出本项目的站位数据

本流程不要求先确认真实球场尺寸。未知尺寸使用上游相对模板（长 12000、宽 7000 的模板单位），输出 0～100 的相对坐标；模板单位不代表实际球场厘米。新流程将禁区深度和宽度修正为 1650、4032 厘米对应的模板标线。未知长宽时，内部标线与实际场地的比例仍可能有偏差，所以归一化不能消除模板偏差。本版不输出米制距离、速度或全场跑动指标。

在仓库根目录执行（macOS，已缓存 SigLIP）：

```bash
export HF_HOME="$PWD/.cache/huggingface"
export HF_HUB_OFFLINE=1
./.venv/bin/python -m examples.soccer.analyze \
  --source examples/soccer/data/2e57b9_0.mp4 \
  --output-dir outputs/match-01 --device auto --save-video
```

Windows PowerShell 使用相同参数，将 Python 路径替换为 `.\.venv\Scripts\python.exe`；设置缓存使用 `$env:HF_HOME = "$PWD/.cache/huggingface"`。模型未缓存完整时不要设置离线模式。短片验收可加 `--max-frames 50`，输出目录必须是新的，避免覆盖实验结果。

输出包括：

- `positions.csv`：每条已确认跟踪观测的时间、编号、角色、球队、检测置信度、画面落脚点、相对坐标、有效性和异常原因，仅含球员与守门员。
- `analysis.json`：相同观测及逐帧映射状态、帧率、参数、模板信息、尺寸来源和处理完成状态。无球员的帧也会保留；处理异常时保留已有结果并标记 `error`。
- `observations.mp4`：加 `--save-video` 时生成，画面上显示跟踪编号、球队及坐标有效性，便于对照。

关键口径：时间戳为从 0 开始的 `frame_index / fps`，不是比分牌时间；输入按恒定帧率解释，变帧率素材需先转换。坐标原点为模板左上角，x 沿长度、y 沿宽度。球队 0/1 为本次聚类编号，不是主客队；跟踪编号不是球衣号码，镜头切换后不保证身份连续。守门员球队按画面内两队中心的距离估计；两队样本不齐全时记为未知。

映射初始实验参数为关键点置信度 0.5、至少 6 个 RANSAC 内点、内点比例至少 0.6、图像空间误差阈值 8 像素，均可通过命令行调整并随结果保存。这些是待实验评估的参数，不是已验证的精度承诺。

映射失败帧不沿用历史矩阵；越界点保留原数值并标记 `out_of_bounds`，不裁剪。其他原因包括 `missing_keypoints`、`insufficient_keypoints`、`degenerate_keypoints`、`insufficient_inliers`、`mapping_failed`、`non_finite_coordinate`。观测中的 `frame_mapping_invalid` 需要结合对应帧的具体失败原因读取。`coordinate_valid` 仅表示通过本版几何检查，不能证明真实位置准确，也不包含球队/身份正确性判断。

可通过 `--pitch-profile examples/soccer/pitch-profile.example.json` 提供尺寸及来源。状态 `unknown` 表示未知、`reference` 表示参考资料、`verified` 表示提供者已核实；程序不会自行把参考资料升级为历史比赛的真实尺寸。此版本只读取提供的资料，比赛候选确认、联网尺寸检索与来源核验尚未接入。

### 不重新识别视频生成轨迹和热区

```bash
python3 -m examples.soccer.report \
  --input outputs/match-01/analysis.json \
  --output outputs/match-01/report.html
```

报告只依赖 Python 标准库，不访问视频、模型或网络。只使用有效坐标，轨迹在无效/漏检帧处断开；热区表示可见目标的有效观测次数，受镜头覆盖影响。浏览器打开 HTML 即可查看，字体优先使用微软雅黑。

### 同一帧的原画面与站位核对

```bash
./.venv/bin/python -m examples.soccer.review \
  --input outputs/match-01/analysis.json \
  --output outputs/match-01/review.html --samples 15
```

该页面从原视频均匀抽取 15 帧，左右同步显示同一时刻的落脚点、跟踪编号与二维位置。点击编号可突出两侧目标；无效观测在原画面标叉，不显示为有效站位。页面内嵌抽帧图片，生成后可以离线打开；生成时需要原视频与 OpenCV，但不会运行模型。原点方向以模板为准，不自动代表进攻方向。

核对页和轨迹热区报告使用同一套 SVG 球场标线，包含两端禁区、小禁区、禁区弧、罚球点、球门、中圈、中线及角球弧。标线按该次分析保存的模板比例绘制，便于检查球员与边线、禁区线的关系；补全标线不改变已有坐标，也不代表真实场地尺寸已被确认。

需要核对突变前后时，可用 `--frames 357 358 359` 指定原视频帧编号，替代均匀抽帧。按钮在选定的抽查点间切换，并不保证每次只前进一帧。

### 复用关键点离线比较参数

新版 `analysis.json` 的每帧额外保存原始关键点及置信度，可在完全相同的球员观测上比较映射参数：

```bash
./.venv/bin/python -m examples.soccer.evaluate \
  --input outputs/match-01/analysis.json \
  --output outputs/match-01/comparison.json --thresholds 8 16
```

比较工具仅使用 NumPy/OpenCV 和保存的数据，不访问视频、球队模型或网络。它输出通过检查的帧数、有效观测数、越界数、拟合内点重投影误差和连续观测的位置变化。拟合内点误差不是独立真值误差，位置变化也不等于速度；不能只按有效率选择正式参数。旧结果没有保存关键点时会明确提示，不生成伪造的对照结果。

### 禁区与中场之间的偏差诊断

仅把坐标归一化并不能消除错误模板比例带来的偏差。第二段样本的原拟合主要采用中圈附近的点，曾把禁区附近的点排除，造成局部一致但远端外推偏差。现提供显式的实验策略，不更改旧默认：

```bash
./.venv/bin/python -m examples.soccer.remap \
  --input examples/soccer/data/validation-0bfacc-16px/analysis.json \
  --output-dir outputs/0bfacc-refined \
  --pitch-profile examples/soccer/profiles/0bfacc-reference.json \
  --anchor-policy structural --require-region-support
./.venv/bin/python -m examples.soccer.review \
  --input outputs/0bfacc-refined/analysis.json \
  --output outputs/0bfacc-refined/review.html --samples 10 --overlay-lines
```

`structural` 排除数组位置（从 1 计）11、12、19、20 的虚拟延长线交点，以及 31、32 的中圈侧向辅助点；保留真实标线交点、角点、罚球点和中线与中圈的交点。`--require-region-support` 要求某个球场区域已有至少 2 个入选点时，该区域也至少保留 2 个内点，避免静默丢掉整片区域后向外推断。关键点不足的帧继续标记无效，不用插值补齐。

原视频的场馆标牌提示 Stuttgart，当前场馆官网列出 105×68。该资料只在专用 profile 中标记为 `reference`，不保证片段的历史真实尺寸，也不自动用于所有比赛。`remap` 保留原有时间、脚点、球队及身份，仅重算坐标。新分析也可显式传入上述策略参数。

`--overlay-lines` 会在核对页增加黄色反投影线开关：应检查它是否贴合原视频的白色禁区线、中线、边线与中圈。反投影仍基于当前拟合，不是额外的人工真值。详细对照见 [验证记录中的偏差诊断](docs/mapping-validation.md)。

验证几何错误和导出一致性：`./.venv/bin/python -m unittest discover -s tests -v`。

2026 年 11 月 12 日新增流程实测：同一示例的前 50 帧，默认 8 像素阈值全部因内点不足被拒绝，保留为 `analysis-check-01`；显式设置 `--ransac-pixels 16` 的对照结果保存在 `analysis-check-16px`，共 1008 条观测、799 条通过几何检查、209 条无效，40 帧通过映射检查。两组均在 `examples/soccer/data/` 下，未提交 Git。CSV/JSON 逐条核对一致，标注视频为 50 帧且末帧可读；使用系统 Python 从保存的 JSON 生成了离线 HTML。16 像素仅为实验对照，未更改默认参数，这些数字不是定位准确率。新增流程尚未完成完整 750 帧和 Windows 实机验证。

后续完整片段与第二样本的验证见 [映射参数验证记录](docs/mapping-validation.md)。正式默认参数尚未确定。

## 基础可见球员指标

读取已保存的站位 JSON 即可计算，无需模型、视频或网络；此命令只使用 Python 标准库。守门员口径必须显式指定，尚未设定项目默认：

```bash
python3 -m examples.soccer.tactics \
  --input examples/soccer/data/validation-0bfacc-refined/analysis.json \
  --output-dir outputs/tactics-outfield --goalkeepers exclude
```

`--goalkeepers exclude` 仅统计非守门员，`include` 同时包含守门员。输出 `metrics.csv`、`metrics.json` 和交互式 `report.html`。报告包含逐帧球队中心、坐标范围框，以及宽度、纵向跨度、中心 x/y、有效人数的五组时间图。统计口径及公式保存在 JSON 中，供后续分析工具读取。

| 指标 | 定义 | 单位 |
| --- | --- | --- |
| 中心 x / y | 有效可见球员坐标的算术平均 | 球场长度 / 宽度百分比 |
| 横向宽度 | max(y) − min(y) | 球场宽度百分比 |
| 纵向跨度 | max(x) − min(x) | 球场长度百分比 |
| 有效候选人数 | 当前口径下通过坐标与身份基本检查的目标数 | 人 |

至少两名不同目标才输出中心及跨度，可通过 `--min-players` 提高门槛；这只是可计算门槛，不表示完整阵型可被可靠观察。映射无效、坐标无效、球队未知、重复跟踪编号和非有限坐标均不能直接参与计算。一个跟踪编号在同帧重复时，该编号的候选全部排除。非守门员超过 10 人、守门员超过 1 人或总数超过 11 人时，相应球队指标标为缺失，需要检查检测与球队分类。原观测不删除。

每帧保留两队记录；不可计算时中心与跨度为 JSON `null` / CSV 空单元格，而不是零。`visible_count` 字段是有效候选人数，不是实际全队人数或画面内总人数。报告不跨缺失帧连线，不平滑、不换算米制值，也不自动判断进攻方向；纵向跨度不应直接称为进攻纵深。曲线受画面覆盖、映射与球队分类影响，不能单凭曲线判断战术意图。

2026 年 11 月 13 日验证：在改进版第二段 250 帧上，每种守门员口径均输出 500 条球队逐帧记录。其中 328 条可计算、144 条因帧映射无效缺失、28 条因角色人数超过上限缺失。两种口径保留为 `tactics-outfield`、`tactics-all` 两份本地预览，口径选择仍待用户确认；输出未提交 Git。CSV/JSON 的记录数、帧号、球队与可用性已核对，页面时间轴、缺失状态和五组曲线已检查；共 16 项自动测试通过。

## 研究与复现约定

- 保留上游代码历史、版权声明及许可证；自有功能与上游基线分开记录。
- 固定测试视频、模型版本和参数，保存检测、跟踪、映射及战术指标的评估结果。
- 对镜头切换、遮挡、非比赛镜头、球场关键点不足等情况记录失败原因，不生成没有数据依据的结论。
- 不提交下载的模型权重、大型比赛视频或个人密钥。使用比赛素材前确认版权和使用条件。

## 来源与许可

本仓库以 [Roboflow Sports](https://github.com/roboflow/sports) 为视觉基线，导入时对应上游提交 `42c80c0`。上游代码采用 [MIT 许可证](LICENSE)，原首页说明见 [README_UPSTREAM.md](README_UPSTREAM.md)。足球示例还依赖 Ultralytics YOLO 等第三方组件；使用、发布或部署时应分别核对其许可证与模型权重、数据集的使用条款。本项目后续自行新增的代码和实验会在提交记录中区分。
