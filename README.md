# 基于深度学习与智能体的足球战术分析系统的设计与实现

本仓库是计算机科学与技术专业本科毕业设计项目，目标是从**足球比赛电视转播视频**中提取可核查的战术数据，并由智能体基于这些数据提供战术问答与解释。

> 当前状态：**视觉算法基线已导入，毕设功能尚在设计与开发阶段。** 仓库目前主要包含 [Roboflow Sports](https://github.com/roboflow/sports) 的原始代码及足球示例；尚未实现本项目自己的战术指标、智能体或完整系统界面。以下“规划功能”不代表已经完成。

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

macOS：

```bash
./.venv/bin/python examples/soccer/prepare_assets.py --include-samples
./.venv/bin/python examples/soccer/main.py \
  --source_video_path examples/soccer/data/2e57b9_0.mp4 \
  --target_video_path examples/soccer/data/2e57b9_0-radar.mp4 \
  --device auto --mode RADAR --no-preview
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe examples/soccer/prepare_assets.py --include-samples
.\.venv\Scripts\python.exe examples/soccer/main.py `
  --source_video_path examples/soccer/data/2e57b9_0.mp4 `
  --target_video_path examples/soccer/data/2e57b9_0-radar.mp4 `
  --device auto --mode RADAR --no-preview
```

`--no-preview` 只保存结果视频，不打开 OpenCV 窗口；去掉即可边处理边预览。程序会打印实际选择的设备。若要处理自己的视频，将 `--source_video_path` 换成视频路径即可；带空格的路径需要加引号。更多基线模式见 [足球示例 README](examples/soccer/README.md)。

### 双平台验收

使用同一段短视频，分别记录 Windows 和 macOS 上的 Python/PyTorch 版本、显卡与实际推理设备，并确认：依赖安装成功、三个模型可读取、`RADAR` 能处理完整片段、输出视频可播放。遇到模型不支持 GPU 或显存不足时，先用 `--device cpu` 排查功能问题，再处理加速兼容问题。

安装 PyTorch 后可先做设备检查。Windows PowerShell（预期 CUDA 为 `True`，且能在 CUDA 上创建张量）：

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available()); print(torch.ones(1, device='cuda'))"
```

Apple 芯片 Mac（预期 MPS 为 `True`）：

```bash
./.venv/bin/python -c "import torch; print(torch.__version__, torch.backends.mps.is_available())"
```

## 研究与复现约定

- 保留上游代码历史、版权声明及许可证；自有功能与上游基线分开记录。
- 固定测试视频、模型版本和参数，保存检测、跟踪、映射及战术指标的评估结果。
- 对镜头切换、遮挡、非比赛镜头、球场关键点不足等情况记录失败原因，不生成没有数据依据的结论。
- 不提交下载的模型权重、大型比赛视频或个人密钥。使用比赛素材前确认版权和使用条件。

## 来源与许可

本仓库以 [Roboflow Sports](https://github.com/roboflow/sports) 为视觉基线，导入时对应上游提交 `42c80c0`。上游代码采用 [MIT 许可证](LICENSE)，原首页说明见 [README_UPSTREAM.md](README_UPSTREAM.md)。足球示例还依赖 Ultralytics YOLO 等第三方组件；使用、发布或部署时应分别核对其许可证与模型权重、数据集的使用条款。本项目后续自行新增的代码和实验会在提交记录中区分。
