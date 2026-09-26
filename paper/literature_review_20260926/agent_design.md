# 顶会 agent / workflow 论文的写作风格调研

调研日期：2026-09-26。本报告只研究优秀论文如何写作，接受用户已经确定的研究定位，不进行研究内容相似性或创新性判断。目标稿件：**More Programs or More Rolls? Separating Coverage from Specialization in LLM Harnesses**。

## 一、值得学习的共同写法

优秀论文让读者很快知道作者要解释什么：摘要先交代具体问题，再给核心想法，最后选择代表性证据；引言让每一段完成一个动作；结果段先说发现，再给表图，最后解释其意义。句子沿着“对象—动作—结果”推进，一句通常只介绍一个核心概念。

当前写作最值得学习 **ReAct 的概念对照与结果解释、SWE-agent 的具体例子和行为叙事、DSPy 的清楚定义与表格、Self-Refine 的简洁过程描述**。ADAS、AFlow、GEPA适合学习问题提出和主图组织；DEI适合学习如何由首图中的现象自然提出问题。排序只表示写作适配度。

## 二、核实的风格样本

正式录用、展示标签和引用数分别记录。review原始分数未完整核验，不把展示标签换称审稿分数。Semantic Scholar API于 **2026-09-26 08:04:39 UTC** 返回的计数为ReAct **11,549**、DSPy **1,030**、ADAS **331**、AFlow **379**，已读取核对数据库原始记录。[引用数证据](E:/projects/AI4AI-Harness/paper/literature_review_20260926/bibliometrics/semantic_scholar_batch.json)

| 样本 | 正式身份 | 主要学习对象 | 来源 |
|---|---|---|---|
| Automated Design of Agentic Systems | ICLR 2025 Poster | 引言层级、问题命名、总览图 | [论文](https://proceedings.iclr.cc/paper_files/paper/2025/file/36b7acf6f6010652b3f2a433774a66fe-Paper-Conference.pdf)、[会议](https://iclr.cc/virtual/2025/poster/28073) |
| AFlow | ICLR 2025 Oral | 摘要次序、贡献条目、性能与成本图 | [论文](https://proceedings.iclr.cc/paper_files/paper/2025/file/5492ecbce4439401798dcd2c90be94cd-Paper-Conference.pdf)、[Oral清单](https://iclr.cc/virtual/2025/events/oral) |
| DSPy | ICLR 2024 Spotlight Poster | 概念定义、段落连接、可读表头 | [论文](https://proceedings.iclr.cc/paper_files/paper/2024/file/f1cf02ce09757f57c3b93c0db83181e0-Paper-Conference.pdf)、[会议](https://iclr.cc/virtual/2024/poster/17642) |
| ReAct | ICLR 2023官方top 5% paper | 平行概念、具体例子、解释性结果段 | [全文](https://arxiv.org/pdf/2210.03629)、[会议](https://iclr.cc/virtual/2023/poster/11003) |
| Reflexion | NeurIPS 2023 Main Conference | 摘要的对象、动作、反馈、结果次序 | [正式记录](https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html) |
| Self-Refine | NeurIPS 2023 Main Conference | 简单过程、首图、任务分组解释 | [论文](https://proceedings.neurips.cc/paper_files/paper/2023/file/91edff07232fb1b55a505a9e9f6c0ff3-Paper-Conference.pdf) |
| SWE-agent | NeurIPS 2024 Main Conference | 具体问题、系统定义、行为案例 | [论文](https://proceedings.neurips.cc/paper_files/paper/2024/file/5a7c947568c1b1328ccc5230172e1e7c-Paper-Conference.pdf) |
| Toolformer | NeurIPS 2023 Main Conference | 从具体例子落到少量设计要求 | [论文](https://proceedings.neurips.cc/paper_files/paper/2023/file/d842425e4bf79ba039352da0f658a906-Paper-Conference.pdf) |
| AgentVerse | ICLR 2024 Poster | 对象、评价范围和行为分析的顺序 | [会议摘要](https://iclr.cc/virtual/2024/poster/19109) |
| AutoGen | COLM 2024 accepted list | 抽象对象的简洁定义、并列列举 | [录用表](https://colmweb.org/2024/AcceptedPapers.html)、[论文](https://openreview.net/attachment?id=BAakY1hNKS&name=pdf) |
| GEPA | ICLR 2026 proceedings | 资源问题、学习曲线、结果分层 | [论文](https://proceedings.iclr.cc/paper_files/paper/2026/file/0e9e708b6f48e14fd0ac29e167413f76-Paper-Conference.pdf) |
| Diversity Empowers Intelligence (DEI) | ICLR 2025 proceedings | 首图现象—问题—流程、问题式章节 | [论文](https://proceedings.iclr.cc/paper_files/paper/2025/file/d7b50b8ac2c781a12f26155f48310d8d-Paper-Conference.pdf) |

DSPy会议页题名末尾为State-of-the-Art Pipelines，正式PDF为Self-Improving Pipelines，元数据同时记录。AFlow的Oral由官方口头报告清单确认。

## 三、八篇目标章节精读

### ReAct：平行概念与解释性结果

摘要用reasoning/acting建立平行结构，随后各用一个分句说明作用。§1先给具体情景，再抽象出问题。§3.3先陈述结果，再借Table 2的失败类别解释；Table 1与Fig.2分别承担总体比较和采样变化的角色。[摘要、§1、§3.3、Tables 1–2、Fig.2](https://arxiv.org/pdf/2210.03629)

**可模仿动作：** 两个概念放在相同语法位置，读者容易记住。结果段使用“比较句—证据句—解释句”；短结论句起步，较长句解释。当前稿的三个问题可以使用平行问句，随后在各节反复沿用同一组关键词。

### SWE-agent：用具体操作理解抽象对象

摘要提出interface；§1用编辑文件和获得反馈的情景说明问题。Fig.1将接口放在agent与computer之间。§4使用短标签安排实验设定。§5.1将消融、行为描述和例图连接，使读者沿着行为理解数字。[摘要、§1、§4–5.1、Fig.1、Table 3](https://proceedings.neurips.cc/paper_files/paper/2024/file/5a7c947568c1b1328ccc5230172e1e7c-Paper-Conference.pdf)

**可模仿动作：** 先说熟悉的动作，再给专业名称；先写发生了什么，再解释。使用操作动词，减少抽象形容词。轨迹段可以先给极短的过程片段，再连接汇总发现。实验设定按固定顺序介绍对象、执行、选择、评分。

### Self-Refine：一个容易复述的过程

摘要把过程拆成生成、反馈、修订，Fig.1围绕循环展开；§2按同样次序写方法。结果先总览，再按任务类型解释，§3.3给不同任务各自的解释空间。[摘要、§1–3.3、Fig.1、Table 1](https://proceedings.neurips.cc/paper_files/paper/2023/file/91edff07232fb1b55a505a9e9f6c0ff3-Paper-Conference.pdf)

**可模仿动作：** 少量关键词在摘要、图、正文重复，用逐步增加的精确性帮助记忆。方法句用时序连接；结果一段一个模式。当前写作可让核心评价流程只围绕三个固定动作展开，避免同一对象不断更名。

### ADAS：由总问题走向具体工作

§1依次安排背景、设计负担、研究问题、命名和具体算法。§2分解对象，Fig.1提供视觉锚点。§4按设置、基线和结果分析组织段落。[摘要、§1–4、Fig.1](https://proceedings.iclr.cc/paper_files/paper/2025/file/36b7acf6f6010652b3f2a433774a66fe-Paper-Conference.pdf)

**可模仿动作：** 一个段落只有一个主导动作：提出、定义、说明或发现。大问题之后迅速落到实际工作。可以给当前引言每段标一个动词，检查段内句子是否都服务于它；段末自然引出下一段。

### AFlow：摘要压缩与贡献结构

摘要依次写困难、问题表达、方法和代表性结果。引言末尾用三个命名条目组织贡献。§5.1集中说明设置；Fig.4让性能和成本在同一坐标系中呈现，其他结果另用表格承载。[摘要、§1、§5、Fig.4、Table 2](https://proceedings.iclr.cc/paper_files/paper/2025/file/5492ecbce4439401798dcd2c90be94cd-Paper-Conference.pdf)

**可模仿动作：** 摘要每句向前推进一个动作，贡献项的第一小句能独立读懂。需要共同理解的量放在同一图内。当前摘要可按“问题—区分—设计—发现—意义”组织，不用一个长句塞满实验细节。

### DSPy：清楚定义与清楚比较

§1先说明具体困难，再分别介绍编程对象、编译器、评价。§3用短定义和小例子解释抽象概念。§6/Table 1用结构化表头区分条件，正文按发现次序解释。[摘要、§1、§3、§6/Table 1](https://proceedings.iclr.cc/paper_files/paper/2024/file/f1cf02ce09757f57c3b93c0db83181e0-Paper-Conference.pdf)

**可模仿动作：** 一句总定义，下一句分解，第三句举例。短句承担定义，长句承担解释。表头表现比较条件，正文只说明主要模式，不逐行复述。术语介绍后立即使用，减少连续的新名词。

### DEI：先让读者看见一个现象

Fig.1由结果矩阵、汇总表现和处理流程组成，读者先看见现象，再理解文章的问题。§4.2–4.3用明确问题引导结果与分析，接着给图、观察、解释。[Fig.1、§4.2–4.3、Fig.3](https://proceedings.iclr.cc/paper_files/paper/2025/file/d7b50b8ac2c781a12f26155f48310d8d-Paper-Conference.pdf)

**可模仿动作：** 图建立直觉，正文把直觉变成可回答的问题。段首先给观察，中间指向可见模式，末尾解释。当前首图应帮助读者在长定义前看懂现象；面板顺序与正文顺序一致。

### GEPA：预算轴与结果层次

摘要从昂贵rollouts引出核心想法。Fig.1将学习曲线与测试结果标记放在一起。§2将资源约束写入问题；§4按观察次序组织结果，扩展应用另设位置。[摘要、§1–4、Fig.1、§5](https://proceedings.iclr.cc/paper_files/paper/2026/file/0e9e708b6f48e14fd0ac29e167413f76-Paper-Conference.pdf)

**可模仿动作：** 用具体资源困难引出一个清楚问题，结果经常回到开头问题。主结果完成连续论证后再展开补充分析。摘要结尾写这项研究使读者理解了什么，而不继续添加实验项目。

## 四、四篇筛读的局部写法

- **Reflexion**：摘要按对象、方式、反馈过程、评价范围、结果推进。学习连续动词带领读者跟踪过程。[摘要](https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html)
- **Toolformer**：引言从具体例子转向少量设计要求。学习先写可认识的现象，再命名抽象目标。[§1](https://proceedings.neurips.cc/paper_files/paper/2023/file/d842425e4bf79ba039352da0f658a906-Paper-Conference.pdf)
- **AgentVerse**：摘要先定义对象，再写范围，最后写行为分析。学习整齐的并列语法与一句一种信息。[摘要](https://iclr.cc/virtual/2024/poster/19109)
- **AutoGen**：开头直接定义，随后简短列举属性与应用。学习定义句的直接性和列举句的紧凑节奏。[论文入口](https://openreview.net/attachment?id=BAakY1hNKS&name=pdf)

## 五、后续改写的具体动作

**摘要：** 问题、核心区分、设计、发现、意义各承担一句；保留最有记忆点的数字。

**引言：** 每段完成一个动作，首句给方向，末句引出下一步。用具体小例子接近读者，逐步进入术语。

**结果：** 结论→关键数字→图中模式→含义或下一个问题。小节标题直接告诉读者发现，正文解释它如何得到。

**图注：** 首句说图让读者看到什么，再解释面板与符号。表头呈现比较条件，正文解释主要关系。

**语言节奏：** 短句定位，后句展开；同一关键词保持一致；主动动词取代长名词串。以下为原创句式示意，不摘录原文，也不代表已写入论文：

> A larger collection creates more opportunities to succeed. The question is what those opportunities reveal.

> The repeated runs reveal a consistent pattern. Figure X shows where that pattern occurs.

> This observation answers the first question. The next experiment examines whether the pattern persists.

正式文本应自然变化句长，避免把段落机械套成模板。

## 六、调研记录

12篇正式录用样本，8篇目标章节精读，4篇筛读。17个搜索query、逐篇来源与阅读位置保存在 `agent_design_sources.json`。GEPA和DEI的官方入口由主代理提供后独立核读。录用标签来自会议，写作观察来自原论文，引用量来自保留的API记录。OpenReview部分页面触发验证，review分数未核。PDF图表叙事以正文、图注和表格文本为据，未声称完成视觉设计审计。
