# 优秀论文与企业技术报告：全文改写风格调研

调研日期：2026-09-26。目标稿件：*More Programs or More Rolls? Separating Coverage from Specialization in LLM Harnesses*。本报告接受用户已经人工复核的研究定位，集中研究写法：怎样提出问题、讲清设计、组织结果、解释图表，以及让技术细节服务于一条连贯故事。以下编辑规则供本轮全文改写使用。

**建议采用的整体风格是：用顶会实证论文的鲜明问题统领全文，用成熟企业报告的直接、具体和清楚分层展开材料。** 读者先知道研究在问什么、做了什么、发现什么，然后自然进入方法与解释。当前稿最适合始终围绕 programs、rolls、coverage、repeatability、selection 这组稳定词汇推进。

## 1. 最值得组合学习的风格

| 写作任务 | 首选范本 | 要借鉴的语言动作 |
|---|---|---|
| 让开篇有清楚张力 | Lottery Ticket、Rethinking Demonstrations、Snell | 一句具体问题，随后给容易理解的比较 |
| 让抽象对象容易认识 | Chain-of-Thought、SWE-agent、Tree of Thoughts | 具体例子或首图先出现，再给正式名称 |
| 让方法容易复述 | Self-Refine、DSPy、Kimi K2 | 固定少量动作词，按作用与执行次序解释 |
| 让结果形成连续故事 | RouteLLM、Implementation Matters、ReAct | 上一观察引出下一问题，段首直接给发现 |
| 让数字与图注可读 | Statistical Precipice、Taori et al. | 正文解释主要模式，图注给读法，表格装完整数值 |
| 让全文具有成熟报告的节奏 | DeepSeek-R1/V3、Kimi K1.5/K2、GLM-4.5 | 先给全貌，分层展开关键选择，最后提炼研究经验 |

选择的是局部表达技巧，不需要将整篇稿件套入某一篇范文的章节模板。上述判断来自本次原文目标章节阅读；具体锚点见分组报告。这里的综合规则是面向当前稿的编辑方案。

## 2. 优先阅读的十二篇正式接收论文

排序按写作借鉴的顺序，而非论文质量排名。会议身份采用正式发表年份。引用量统一来自 **2026-09-26 Semantic Scholar Graph API 快照**；链接指向对应聚合记录，不能将其解释为单独会议版本的引用量。UNKNOWN 表示本轮没有可靠计数。展示形式、奖项与审稿分数分别记录。

| 顺序与论文 | 已核实身份或荣誉 | 引用快照 | 优先看哪里、学什么 |
|---|---|---:|---|
| 1. *Rethinking the Role of Demonstrations: What Makes In-Context Learning Work?* | [EMNLP 2022 main](https://aclanthology.org/2022.emnlp-main.759/) | UNKNOWN | 摘要、第一页 Fig.1、§4–5；发现尽早出现，小节回答连续问题 |
| 2. *Scaling LLM Test-Time Compute Optimally Can be More Effective than Scaling Parameters for Reasoning* | [ICLR 2025 Oral](https://iclr.cc/virtual/2025/oral/31924) | [2,192](https://www.semanticscholar.org/paper/8292083dd8f6ae898ea0ee54a6b97997d1a51c9d) | 摘要、§1、§5.2；问题带条件，趋势先于解释 |
| 3. *The Lottery Ticket Hypothesis: Finding Sparse, Trainable Neural Networks* | [ICLR 2019 Best Paper](https://iclr.cc/Conferences/2019/Awards) | [4,470](https://www.semanticscholar.org/paper/21937ecd9d66567184b83eca3d3e09eb4e6fbd60) | 摘要、§1、Fig.1；经验张力、视觉比较、正式命名 |
| 4. *Chain-of-Thought Prompting Elicits Reasoning in Large Language Models* | [NeurIPS 2022 main](https://papers.neurips.cc/paper_files/paper/2022/hash/9d5609613524ecf4f15af0f7b31abca4-Abstract-Conference.html) | [22,167](https://www.semanticscholar.org/paper/1b6e810ce0afd0dd093f789d2b2742d047e316d5) | Fig.1、§3.3–3.4；极小例子帮助理解，后续实验由读者疑问引出 |
| 5. *ReAct: Synergizing Reasoning and Acting in Language Models* | [ICLR 2023 In-Person Poster / top 5% paper](https://iclr.cc/virtual/2023/poster/11003) | [11,549](https://www.semanticscholar.org/paper/99832586d55f540f603637e458a292406a0ed75d) | 摘要、§1、§3.3；平行概念、比较句、解释性例子 |
| 6. *Deep Reinforcement Learning at the Edge of the Statistical Precipice* | [NeurIPS 2021 Outstanding Paper Award](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html) | [1,021](https://www.semanticscholar.org/paper/558ca2e8c7eb56edd77a52b084e6cc24dffe5bcd) | §3、Figs.2/5、Table 1；结果段首、读图说明与附录分工 |
| 7. *Rethinking the Value of Network Pruning* | [ICLR 2019 正式作者版](https://arxiv.org/pdf/1810.05270) | [1,699](https://www.semanticscholar.org/paper/4a1004ecd34118116344633c7cdcc34493c423ee) | §1、§3–4、§7；常见做法、具体比较、结果含义的次序 |
| 8. *RouteLLM: Learning to Route LLMs from Preference Data* | [ICLR 2025 Poster](https://iclr.cc/virtual/2025/poster/30737) | [710](https://www.semanticscholar.org/paper/9b3239cff17327960804098e33e1ca903e7b9e85) | §1、§5.1–5.5；目标使用平行语法，实验标题有明确问题 |
| 9. *DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines* | [ICLR 2024 Spotlight Poster](https://iclr.cc/virtual/2024/poster/17642) | [1,030](https://www.semanticscholar.org/paper/2069aaaa281eb13bcd9330fc4d43f24f6b436a53) | §3、§6/Table 1；定义、分解、例子以及结构化表头 |
| 10. *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering* | [NeurIPS 2024 main](https://proceedings.neurips.cc/paper_files/paper/2024/file/5a7c947568c1b1328ccc5230172e1e7c-Paper-Conference.pdf) | [1,853](https://www.semanticscholar.org/paper/1c3c531fc0fbe79f97f367ed3648de8467caeeaa) | Fig.1、§4–5.1；具体操作、清晰设置、行为叙事 |
| 11. *Tree of Thoughts: Deliberate Problem Solving with Large Language Models* | [NeurIPS 2023 main](https://proceedings.neurips.cc/paper/2023/hash/271db9922b8d1f4dd7aaef84ed5ac703-Abstract.html) | [4,940](https://www.semanticscholar.org/paper/2f3822eb380b5e753a6d579f31dfc3ec4c4a0820) | Fig.1、§3、§4.1；统一视觉语法、总结果后展开解释 |
| 12. *Self-Refine: Iterative Refinement with Self-Feedback* | [NeurIPS 2023 main](https://proceedings.neurips.cc/paper_files/paper/2023/file/91edff07232fb1b55a505a9e9f6c0ff3-Paper-Conference.pdf) | [4,755](https://www.semanticscholar.org/paper/3aaf6a2cbad5850ad81ab5c163599cb3d523436f) | 摘要、Fig.1、§2–3.3；少量固定动词解释一个过程 |

此外，Self-Consistency 的 [ICLR 2023 正式记录](https://iclr.cc/virtual/2023/poster/11718)与 [7,730 次引用](https://www.semanticscholar.org/paper/5f19ae1135a9500940978104ec15a5b8751bc7d2)已核实，本轮为摘要筛读；AFlow 的 [ICLR 2025 Oral](https://iclr.cc/virtual/2025/events/oral)与 [379 次引用](https://www.semanticscholar.org/paper/53132ea6c107479d4557631299d3ed525109b464)也已核实，完成目标章节精读。它们保留在完整样本库中。DSPy、RouteLLM 在会议页与 PDF 中有题名措辞差异，原始来源表已分别记录。

## 3. 企业技术报告怎样帮助九页论文讲故事

本轮企业阅读共十份原始报告：DeepSeek-V3、DeepSeek-R1、ChatGLM/GLM-4、GLM-4.5、Kimi K1.5、Kimi K2、GPT-4、GPT-4o、Claude 3、Claude 4。前七份按技术报告阅读，Claude 3 为 model card，GPT-4o 与 Claude 4 为安全 system card；文档身份分列。原文入口和指定章节见 [DeepSeek/GLM 分报告](E:/projects/AI4AI-Harness/paper/literature_review_20260926/corporate_deepseek_glm.md)、[Kimi 分报告](E:/projects/AI4AI-Harness/paper/literature_review_20260926/corporate_kimi.md)与 [OpenAI/Anthropic 分报告](E:/projects/AI4AI-Harness/paper/literature_review_20260926/corporate_openai_anthropic.md)。

[GPT-4](https://cdn.openai.com/papers/gpt-4.pdf)适合学习结果与工程解释的先后次序，[Claude 3](https://assets.anthropic.com/m/61e7d27f8c8f5919/original/Claude-3-Model-Card.pdf)适合学习总体表现、代表案例、技术细节的递进；[GPT-4o](https://cdn.openai.com/gpt-4o-system-card.pdf)和 [Claude 4](https://www-cdn.anthropic.com/07b2a3f9902ee19fe39a36ca638e5ae987bc64dd.pdf)提供了总览与细节分层、重复段落结构的局部样例。后两份目录服务于其安全评估用途，当前论文取用局部表达技巧。

| 维度 | 本次企业报告样本的组织倾向 | 对当前主会论文的编辑转译 |
|---|---|---|
| 开头 | 先交代完成的对象与总体表现 | 尽早交代研究问题、核心比较、代表性发现 |
| 技术展开 | 围绕少数训练或系统模块展开 | 围绕回答中心问题所需的少数概念与操作展开 |
| 结果 | 总览图、完整结果表、分类解释分工 | 首图建立直觉，主表承载全貌，正文选择关键模式 |
| 方法解释 | 从观察或需求进入设计选择 | 一两句动机之后写具体操作，最后给必要形式化 |
| 篇幅 | 可容纳较多模块、配置与能力类别 | 主文只展开一条故事，把详细技术材料放到附录 |
| 收尾 | 回到关键成分与完成的工作 | 提炼读者获得的理解，集中交代适用范围与下一问题 |

它们与顶会范文共同值得学习的是明确的对象、稳定的词汇和由浅入深的安排。成熟感来自对材料的组织：作者清楚知道每段负责什么。当前稿可以在摘要、引言末尾和结论中分别完成“预告、展开、提炼”，三处各加一层理解。

九页主文可先按约 15% 引言、20% 概念与研究设计、45% 结果和主图、15% 解释讨论、5% 收尾规划容量；实际版面再据图表调整。这只是编辑工作预算。首图和主结果得到充分解释后，读者需要的配置、推导、完整分组、更多轨迹均可在附录查到。

## 4. 摘要：六句话完成六个动作

以下为本报告原创的功能模板，不是拼接范文句子，也不是已定稿的摘要。句数可随信息量微调，但每句应有一个主要任务。

| 句位 | 功能 | 当前稿的内容 | 原创英文句法 |
|---|---|---|---|
| 1 | 给具体问题 | 固定执行次数下，更多程序与更多重复如何比较 | *With a fixed execution budget, how much do we gain by changing the program rather than running it again?* |
| 2 | 给理解问题的组织方式 | coverage、repeat-stable specialization、selector utility | *We examine this question through three views: [view A], [view B], and [view C].* |
| 3 | 给核心研究设计 | 同代码重复控制与对应比较 | *Our design compares [collection A] with [control B], using [the matching rule].* |
| 4 | 给最容易理解的发现 | 主要覆盖观察与代表性数字 | *Across [the evaluated setting], [the main observation], with [one representative value].* |
| 5 | 给进一步分析的答案 | 重复结果与已执行选择器的结果 | *Repeated runs show [the repeated-run result], while the evaluated selector yields [the selection result].* |
| 6 | 给文章的理解增量 | 研究如何帮助读者理解程序与重复的分配 | *Together, these observations show how [the central relationship] changes the interpretation of [the practical choice].* |

数字优先保留最能帮助读者记住主发现的一两个；其余放在主结果。术语第一次出现时用自然语言解释，符号交给正文。最后一句回到开头问题，形成闭合叙事。

## 5. 引言：六段逐步增加精确性

**第一段让读者认识一个选择。** 从实际执行情景进入：有限执行次数可以分给不同程序，也可以分给同一程序的重复。段末提出标题里的问题。两三句足以让动机具体，随后进入工作本身。

**第二段给可想象的小例子。** 用一个极短的成功/失败情景说明读者会看到怎样的现象。小例子的角色是让研究对象可见；首图可以承担大部分解释。段末自然问：这样的覆盖对应什么样的重复行为？

**第三段建立三个阅读问题。** 将 coverage、repeat-stable specialization 和 selection 放在平行的语法位置。每个概念只用一句话说明它想回答什么。这里先建立直觉，正式统计定义在概念节集中出现。

**第四段给研究设计。** 告诉读者如何比较程序集合与同代码重复，匹配的是哪一种资源，以及数据来自怎样的执行。保持“对象→操作→测量”的顺序。较细的抽样与计算步骤随后在方法中展开。

**第五段提前给总体答案。** 先写主要模式，再选少量数字和直观关系；让读者在读方法前知道结果的方向。选择器已经执行且收益为零，应作为已完成发现直接呈现。随后一句说明后文将如何解释这组结果。

**第六段交代文章带走什么。** 可写成紧凑段落或两三个平行条目，分别对应研究设计、实证发现与解释框架。每一项有具体对象和动作，长度相近。用一句简短路标结束。

可用的原创过渡句：*This example leads to three questions.* / *We make these questions concrete with a paired execution design.* / *The resulting comparison reveals a clear ordering of the evidence.* / *The following sections explain how this pattern arises.* 每个过渡都应承接实际内容，避免机械重复同一种开头。

## 6. 方法与结果：把材料写成推理过程

### 技术方法的叙事顺序

一个方法段可以沿着四步展开：**为什么需要这个操作→具体做什么→如何形式化→输出怎样用于后续分析**。段首以读者能理解的任务起步，公式出现在对象与作用已经清楚之后。公式后用一句话解释最重要的量或方向，接着让它在结果中发挥作用。

原创句法示例：*To compare [two objects], we hold [resource] fixed and vary [the intended factor]. For each task, we [concrete operation]. This produces [measurement], which we use to answer [question].* 定义句可用 *We use [term] to denote [plain description].* 操作句优先用 sample、run、pair、compare、measure 等具体动词。第一次解释完整，后续用固定术语短回指。

方法小节标题用读者认识的任务或对象；内部文件名、运行轮次和修订日志放到复现材料。主文讲最终研究是怎样组织的，附录给读者复现该过程需要的精度。

### 结果段的基本节奏

一段首先陈述观察，其次给最有代表性的比较与数字，再解释图表里哪些模式支持这句话，最后说它如何回答本节问题或引出下一节。不是每段都要四句：清楚的段落可以只有两三句，复杂观察可以拆段。

| 段落职责 | 原创 topic sentence 或衔接示例 |
|---|---|
| 总体比较 | *At a fixed number of executions, [A] achieves [result] relative to [B].* |
| 分解总体结果 | *The aggregate result is concentrated in [the observed subset or pattern].* |
| 回到重复执行 | *Repeated executions reveal how consistently this pattern returns.* |
| 对应图中变化 | *Figure X shows that [visible pattern] varies with [the horizontal-axis quantity].* |
| 呈现零收益 | *The evaluated selector adds no successes over [the stated baseline].* |
| 引入具体例子 | *The following task illustrates the sequence behind this aggregate pattern.* |
| 转向下一问题 | *This observation answers [the first question]; we next examine [the next question].* |

正文只选能够支持段首的一组数字。完整表格承担全量记录，文字承担比较、趋势与解释。条件放在最相关的一处，用短语衔接，避免每个段末重复相同说明。零收益、小差异和方向不一的结果都有明确叙事位置：把它们作为回答问题的观察来写，读者会更容易理解整条研究路线。

### 图注、表格与例子的分工

**首图提供入口。** 用少量对象说明比较关系，面板次序与正文次序一致。核心对象固定颜色、标签与排列。让读者能把图讲成两三句话，再逐步增加信息。

**结果图突出一个阅读问题。** 轴、图例和单位在图中可直接识别；同类面板沿用坐标与命名。图注先说图展示什么，再按面板解释，随后说明统计表示和读法。原创模板：*Figure X. [Main visible comparison]. (a) [Panel A]. (b) [Panel B]. Points show [quantity]; intervals show [specified summary]. [One sentence directing the reader to the key pattern].*

**表格呈现比较条件。** 表头就应让读者分清对象、资源单位和测量；表下注释给符号、缩写与计算口径。正文引用表格时指出要看哪种关系，避免逐行转述。图中的代表性结果与表中的完整数值形成互补。

**轨迹例子解释已经出现的现象。** 先给总体观察，再给一个短小过程片段，最后回到总体结论。只保留能帮助读者理解动作或转折的部分；完整轨迹放附录。

## 7. 对当前稿的具体写作映射

以下映射基于当前研究对象与已有数值文件，供主代理统一改写；不是对正在改动的稿件作逐行审核。

| 稿件内容 | 在故事中的职责 | 建议写法 |
|---|---|---|
| 标题与摘要 | 让 programs/rolls 的选择立即可见 | 保留具体张力，摘要按问题、设计、发现、理解推进 |
| 引言 | 带读者从执行情景进入三个问题 | 一个短例子、三个平行问题、一段设计、一段总体发现 |
| 概念与 coverage 解释 | 让读者清楚每个量回答什么 | 先自然语言、再固定名称、最后给符号 |
| 执行与 same-code controls | 让比较过程可以被复述 | 对象、执行、配对、测量依次说明；匹配资源明确称 executions |
| 主结果 | 给出全貌并解释差异在哪里 | 主要数字和图表先出现，随后分组或分解 |
| repeat-stable analysis | 承接覆盖之后的读者疑问 | 先写重复观察的模式，再解释对应测量 |
| selector utility | 完成从可用覆盖到实际选择的叙述 | 直接报告已执行选择器的零增益结果，再解释其与前面观察的联系 |
| 支撑分析与案例 | 帮助理解主结果 | 按要解释的现象组织，每个例子回到主线 |
| discussion 与 conclusion | 提炼研究经验 | 回答开头问题，集中说明理解与适用情景，简短收尾 |
| 技术附录 | 使完整材料有清楚入口 | 每节开头说明用途；配置、推导、分类表、更多轨迹各自归位 |

当前 [common386_numbers.tex](E:/projects/AI4AI-Harness/paper/latex/common386_numbers.tex)记录主配对任务数 386、比较量 D 为 −0.26、区间 [−1.45, 0.95]、已执行策略增益 0.00。改写时这些已有结果承担具体叙事内容；符号与单位沿用正文定义。不要将已完成的零收益实验写成未来工作。本文的资源名称统一使用实际匹配的执行次数；方法段说明一次，结果沿用。

成熟的讨论可以按“本文使什么关系变清楚→这些观察怎样共同解释开头选择→在哪些实际情景下有用”安排三段。必要范围在相关位置一次说明，末段只留下最自然的一个延伸问题。附录保留完整技术信息，正文保持向前推进。

## 8. 检索、阅读深度与核实范围

会议样本由三个并行分组与补充阅读组成：sampling/selection 9 篇、agent/workflow 12 篇、实证研究写法 12 篇，另有补充正式论文 5 篇，共 **38 篇正式会议样本**。另单列 TMLR 两篇及未核实会议身份的预印本一篇。这个数量表示身份已核实的样本覆盖，不能解释为 38 篇每页通读。

阅读分级在每个来源记录中保留：目标章节结构精读、针对性阅读、摘要筛读。三组核心结构精读分别为 4、8、6 篇；补充阅读注明实际读过的摘要、引言与实验段。十份企业报告均完成注明章节的定点阅读。Schaeffer 使用作者 arXiv v1 作风格阅读，会议接收由 PMLR 核实；Kimi 两篇使用作者 v1；技术报告与最新元数据版本分列。Claude 3 使用现行官方 PDF 的原始主体第 1–12 页，未将后附增补混称原始内容。图表观察以原文、表格和图注为据，本次不称完成视觉排版审计。

检索优先使用正式 proceedings、官方会议页、官方奖项页、作者全文与机构发布页。引用量来自保留的 Semantic Scholar API 返回；不同数据库记录没有混加，题名不匹配的返回已排除。引用快照分别为 2026-09-26 16:04:39 与 16:07:22（北京时间）。

本轮没有取得大多数论文的完整评审数值，因此称“正式接收”“Oral”“Spotlight”“获奖”或“高引用”时均使用对应证据，不概称“高分接收”。C06 公开 review 中能读到一位 reviewer 在 rebuttal 后提及 7，但没有完整评分向量，不计算平均分。所有句法模板为本报告原创，没有逐字复制论文摘要。

详细文件与原始记录：

- [sampling 与 selection](E:/projects/AI4AI-Harness/paper/literature_review_20260926/sampling_selection.md)、[来源 JSON](E:/projects/AI4AI-Harness/paper/literature_review_20260926/sampling_selection_sources.json)
- [agent 与 workflow](E:/projects/AI4AI-Harness/paper/literature_review_20260926/agent_design.md)、[来源 JSON](E:/projects/AI4AI-Harness/paper/literature_review_20260926/agent_design_sources.json)
- [实证研究写法](E:/projects/AI4AI-Harness/paper/literature_review_20260926/critical_evaluation.md)、[来源 JSON](E:/projects/AI4AI-Harness/paper/literature_review_20260926/critical_evaluation_sources.json)
- [补充精读](E:/projects/AI4AI-Harness/paper/literature_review_20260926/additional_readings.md)
- [DeepSeek 与 GLM](E:/projects/AI4AI-Harness/paper/literature_review_20260926/corporate_deepseek_glm.md)、[来源 JSON](E:/projects/AI4AI-Harness/paper/literature_review_20260926/corporate_deepseek_glm.json)
- [Kimi](E:/projects/AI4AI-Harness/paper/literature_review_20260926/corporate_kimi.md)、[来源 JSON](E:/projects/AI4AI-Harness/paper/literature_review_20260926/corporate_kimi.json)
- [OpenAI 与 Anthropic](E:/projects/AI4AI-Harness/paper/literature_review_20260926/corporate_openai_anthropic.md)、[来源 JSON](E:/projects/AI4AI-Harness/paper/literature_review_20260926/corporate_openai_anthropic.json)
- [引用量批次一](E:/projects/AI4AI-Harness/paper/literature_review_20260926/bibliometrics/semantic_scholar_batch.json)、[引用量批次二](E:/projects/AI4AI-Harness/paper/literature_review_20260926/bibliometrics/semantic_scholar_batch2.json)

统一索引现已整理为 [source_registry.csv](E:/projects/AI4AI-Harness/paper/literature_review_20260926/source_registry.csv) 与 [source_registry.json](E:/projects/AI4AI-Harness/paper/literature_review_20260926/source_registry.json)，共 51 个唯一来源：38 篇会议论文、2 篇期刊论文、1 篇单列预印本和 10 份企业报告。其中 22 篇会议论文完成定点结构精读，21 个来源具有核实的引用量记录；逐项保留身份、原文入口、阅读位置与计量证据。定点结构精读不等于逐页全文通读。
