# 足球战术知识库

这是供智能体按问题检索的第一版中文战术知识库。正文存储在 [football_tactics.json](football_tactics.json)，目前有 9 张卡片：7 张战术卡片和 2 张项目口径卡片。每张卡片包括概念摘要、判断所需观测、当前系统支持情况、误判风险和来源。不是模型训练数据，也不是自动战术识别算法。

## 已覆盖内容

| 编号 | 内容 | 主要用途 |
| --- | --- | --- |
| K001 | 高位逼抢 | 区分前场站位与实际施压行为 |
| K002 | 中位防守与低位防守 | 说明防守位置、组织与持续时间要求 |
| K003 | 紧凑性与阵型收缩 | 解释宽度、长度与局部间距的关系 |
| K004 | 丢球反抢与防守转换 | 说明需要球权转换及连续动作依据 |
| K005 | 进攻宽度与拉开空间 | 解释横向展开的作用与限制 |
| K006 | 转移进攻 | 区分球队中心横移和球的跨侧转移 |
| K007 | 局部人数优势 | 区分画面总人数与局部有效多打少 |
| K008 | 本项目的中心、宽度与纵向跨度 | 解释当前统计的公式和百分比口径 |
| K009 | 比赛事实与知识解释的边界 | 防止用一般知识替代本场比赛证据 |

## 来源与编写范围

战术概念来自已查阅的 FIFA Training Centre 官方材料，使用中文概述，不保存或复制整篇文章。每张卡片中的“当前系统支持”和部分“误判风险”由本项目结合现有架构编写，不冒充 FIFA 原文。项目指标卡片引用本仓库的代码和验证记录。

- [高位逼抢及其数据采集口径](https://www.fifatrainingcentre.com/en/game/tournaments/fcwc/2025/team-analyses/increased-use-of-high-press-and-pressing-strategies.php)，2025-11-11，章节 How FPI measures a high press、Sustaining the high press。
- [中位防守与紧凑性](https://www.fifatrainingcentre.com/en/fwc2022/technical-and-tactical-analysis/controlling-the-game-without-the-ball--the-mid-block-and-compactness.php)，2023-05-19，章节 Defining a mid-block。
- [准备和执行丢球反抢](https://www.fifatrainingcentre.com/en/practice/elite-sessions/transition-to-defending/preparing-and-executing-counter-pressing.php)，2023-10-30，概述及训练要点。
- [转移进攻](https://www.fifatrainingcentre.com/en/game/game-analysis/in-possession/switch-of-play.php)，2021-11-08，章节 Principles、Against a well-organised team。
- [人数和空间的作用](https://www.fifatrainingcentre.com/en/practice/training-perspectives/designing-games-for-development/the-role-of-player-numbers-and-space.php)，2026-06-09，章节 Equal numbers v. numerical advantages、Space。

来源核对日期：2026-11-17。知识库保留发布时间、核对日期和原文章节。不将旧文中的赛事数据当作当前比赛事实，也不照搬训练场尺寸或时间规则作为统一分类阈值。

此前收集的 18 篇论文多数服务于检测、跟踪和映射，尚未作为本知识库的已核对正文导入；不能把“目录里有论文”写成“智能体已经理解全部论文”。后续加入论文时，应先核对具体章节，再编写摘要、方法适用条件和来源，不直接批量堆入全文。

## 如何工作

1. 智能体先查询当前比赛数据概况。
2. 涉及战术概念时调用 `search_tactical_knowledge`，按中文术语、同义词或英文名称检索。
3. 本地搜索返回最多 5 张卡片，默认 3 张；不将整个库一次性发送给模型。
4. 涉及比赛数值时另外调用统计工具。
5. 回答将统计证据 `[E编号]` 与知识证据 `[E编号][K编号]` 分开，并附来源。引用不存在或未检索到的卡片时，程序要求重答；仍不合格则报错。

这是基于关键词与双字片段匹配的检索增强生成原型，尚无向量嵌入、语义重排或图数据库。小规模卡片易于审查、可离线检索、兼容 macOS 和 Windows；抽象表达及未收录同义词可能漏检，检索分数不是置信度。库中没有结果时应报告未覆盖。

## 本地检索示例

在仓库根目录运行，不读取密钥、不调用 API：

```bash
python -c "from sports.common.tactical_knowledge import TacticalKnowledgeBase; import json; print(json.dumps(TacticalKnowledgeBase().search('高位逼抢需要什么证据'), ensure_ascii=False, indent=2))"
```

使用现有智能体命令即可结合知识库问答，例如将 `--question` 设置为“请解释球队0在5到10秒的宽度与跨度，是否足以认定高位逼抢？”。检索工具已接入，无需重新识别视频或安装额外依赖。

## 维护与评价

新增卡片沿用唯一编号，填写同义词、摘要、所需证据、当前支持情况和可追溯来源；变更后更新版本字段并跑测试。优先补充经核对的中文教学资料与战术研究论文。官方外文材料可用中文整理；知识库来源数量与毕业论文参考文献的中外文比例是两回事，本次没有修改原有参考文献列表。

评价应分别测量：术语检索命中、来源引用正确性、数值与工具一致性、是否越过证据推断战术，以及不同视频下的表现。当前小规模测试不能证明检索召回率或战术识别准确率；任意模型文本仍需核查，未实现逐句事实验证。
