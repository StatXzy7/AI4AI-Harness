# 优秀论文的写作风格调研：sampling、测试时计算与routing文献组

调研日期：2026-09-26。用途：为 *More Programs or More Rolls? Separating Coverage from Specialization in LLM Harnesses* 提供写作范本。用户已人工复核研究定位，本报告只分析文章如何提问、组织段落、构造句子、安排图表和叙述结果。

本组核实了9篇主会论文，另列2篇期刊论文和1篇尚未核实主会身份的预印本。最值得组合学习的语言动作是：**Snell用具体问题统领全文；Schaeffer以一个疑问串起解释；RouteLLM让段落和图表一一对应；ToT让首图先于术语帮助理解。**

## 1. 风格样本与身份核实

| ID | 文献 | 主会与展示形式 | 本次阅读深度 | 值得学习的写作动作 |
|---|---|---|---|---|
| S1 | Wang et al., Self-Consistency Improves Chain of Thought Reasoning in Language Models | ICLR 2023；官方页为Virtual presentation / poster accept | 官方摘要、会议页 | 用一个操作和一个结果构成标题与摘要中心 |
| S2 | Yao et al., Tree of Thoughts: Deliberate Problem Solving with Large Language Models | NeurIPS 2023 Main Conference；展示等级未核实 | 正式全文：摘要、§1–3、§4.1、Fig.1/3、Table 2 | 统一视觉语法；主结果之后解释原因 |
| S3 | Snell et al., Scaling LLM Test-Time Compute Optimally Can be More Effective than Scaling Parameters for Reasoning | ICLR 2025 **Oral** | 正式全文：摘要、§1–3.2、§5.2、Fig.1/3/4 | 问题式开篇；先概括趋势，再解释条件 |
| S4 | Ong et al., RouteLLM: Learning to Route LLMs from Preference Data | ICLR 2025 Poster | 正式全文：摘要、§1、§3、§4.1、§5.1–5.5、Fig.1、Tables 1–7 | 平行句列目标；按问题命名实验小节 |
| S5 | Feng et al., GraphRouter: A Graph-based Router for LLM Selections | ICLR 2025 Poster | 官方摘要、会议页 | 一句话一个功能的摘要推进 |
| S6 | Schaeffer et al., How Do Large Language Monkeys Get Their Power (Laws)? | ICML 2025，PMLR 267；展示等级未核实 | 接收身份由PMLR核实；风格精读为作者arXiv v1的摘要、§1–5/7、Fig.2–5 | 疑问—回答—解释例子—用途的叙事链 |
| S7 | Setlur et al., Scaling Test-Time Compute Without Verification or RL is Suboptimal | ICML 2025，PMLR 267；展示等级未核实 | 官方摘要 | 用动词区分形式分析与实验观察 |
| S8 | Lakshminarayanan et al., Simple and Scalable Predictive Uncertainty Estimation using Deep Ensembles | NIPS 2017；展示等级未核实 | 官方摘要、原文首页、公开review文字 | 清晰列出实用特点；结果句跟随评价场景 |
| S9 | Xu et al., Hydra: Automatically Configuring Algorithms for Portfolio-Based Selection | AAAI 2010，24(1):210–216；展示等级未核实 | 官方摘要、原文引言 | 平行句介绍两种思路，顺势落到中心问题 |

主任务的Semantic Scholar API快照（2026-09-26 08:04 UTC）记录：[Self-Consistency 7,730次](https://www.semanticscholar.org/paper/5f19ae1135a9500940978104ec15a5b8751bc7d2)、[Snell 2,192次](https://www.semanticscholar.org/paper/8292083dd8f6ae898ea0ee54a6b97997d1a51c9d)、[RouteLLM 710次](https://www.semanticscholar.org/paper/9b3239cff17327960804098e33e1ca903e7b9e85)。原始记录位于本目录bibliometrics/semantic_scholar_batch.json；这些是arXiv关联聚合记录的引用量。第二批API快照（08:07 UTC）另核实[Tree of Thoughts 4,940次](https://www.semanticscholar.org/paper/2f3822eb380b5e753a6d579f31dfc3ec4c4a0820)，原始记录在bibliometrics/semantic_scholar_batch2.json。其余条目引用量为UNKNOWN。评审数值均未核实；Oral与引用量分列，分别表示展示形式和传播情况。S8的公开评审可读，但页面没有数值分数；未核实的award不作标记。

## 2. 四篇精读样本：段落、句法与图表的具体处理

### S3 Snell：让一个问题承担文章的组织工作

**观察位置：**摘要、§1、§5.2、Fig.1/3/4。摘要很快进入一个带条件的问题，随后用编号将分析分成两条线，再依次交代观察、由观察导出的策略和量化结果。引言重复中心问题，但增加研究动机和研究步骤。§5.2的结果段先概括曲线的总体趋势，接着指出随预算变化的转折，最后讨论可能解释。Fig.1承担全文预览，后续图展开细节。[正式全文](https://proceedings.iclr.cc/paper_files/paper/2025/file/1b623663fd9b874366f3ce019fdfdd44-Paper-Conference.pdf)；[Oral核实](https://iclr.cc/virtual/2025/oral/31924)。

**可学的语言动作：**把条件放进提问句；用两三个平行短语给读者建立路线；结果句先给方向，再给数字。当前稿可以用“固定执行次数时，应把执行分配给更多程序，还是同程序的更多重复？”作为组织性提问，然后保持后续小节用同一组名词回答。英文句式可写为：*Given [a fixed resource], how does [choice A] compare with [choice B]?* 这是原创结构示例，不是原文引句。

### S4 RouteLLM：每一节回答一个读者自然会问的问题

**观察位置：**§1、§3、§5.1–5.5、Fig.1、Tables 1–7。引言先给实际使用情境，再用结构一致的三个目标句压缩要求。实验小节从主要结果转向适应性、数据分布、成本和开销，使读者能按问题定位。表后段落先点明该表显示的主要结果，再解释相邻设置之间的变化；有利和不利结果使用相近的陈述密度。Fig.1把方法曲线和指标解释放在一起。[正式全文](https://proceedings.iclr.cc/paper_files/paper/2025/file/5503a7c69d48a2f86fc00b3dc09de686-Paper-Conference.pdf)；[Poster核实](https://iclr.cc/virtual/2025/poster/30737)。

**可学的语言动作：**小节标题使用读者问题中的核心名词；结果段按“观察—具体比较—解释”排列，避免先讲实现步骤。当前稿的selector段可以直接以已完成的零收益结果起句，随后说明对应比较和图表；让零结果和其他结果有同样清楚的主题句。句式可写为：*The selector yields [observed result] under [setting] (Table X).*

### S2 ToT：先让图形建立直觉，再给分解后的说明

**观察位置：**摘要、§1–3、§4.1、Fig.1/3、Table 2。摘要遵循“使用情境—具体困难—方法动作—实验场景—一个代表数字”的顺序。Fig.1用相同矩形和连接方式画多个过程，读者不必先掌握全部术语。§3以四个短问题分解方法，再逐项回答。Table 2给主结果，Fig.3进一步组织规模变化与错误位置，使结果叙述自然转向解释。[正式全文](https://proceedings.neurips.cc/paper/2023/file/271db9922b8d1f4dd7aaef84ed5ac703-Paper-Conference.pdf)；[主会核实](https://proceedings.neurips.cc/paper/2023/hash/271db9922b8d1f4dd7aaef84ed5ac703-Abstract.html)。

**可学的语言动作：**一句话只描述一个动作；先给图中共同元素的含义，再说明分支差异。当前稿首图可用统一符号表示程序、执行、重复和结果，caption第一句说图回答什么问题，后续按面板顺序阅读。方法段可用少量明确问句组织，但不需要复制原文的术语、认知类比或四分法。

### S6 Schaeffer：把读者的疑问延续到下一节

**观察位置：**摘要、§1–5、Fig.2–5。摘要从一个观察转入一个令人想继续读的问题，然后给出解释方向，最后交代用途。节标题承担叙事转场：先问现象是否应当出现，再解释来源，随后处理例外，最后介绍如何使用解释。Fig.2以“整体—组成部分—联系”布局压缩核心思路；Fig.5以流程对照解释两种估计方式。精读版本为arXiv v1，接收身份由PMLR独立核实。[作者全文](https://arxiv.org/pdf/2502.17578)；[ICML记录](https://proceedings.mlr.press/v267/schaeffer25a.html)。

**可学的语言动作：**段末留下具体问题，下一段首句立即作答；用一句短解释接在较密集的技术段后。当前稿可沿既定研究问题安排“看到什么—如何读懂—重复测量说明什么—选择器得到什么结果”的连续叙述。这里借鉴的是推进方式，文章研究对象和定位沿用用户已确定的版本。

## 3. 五篇风格筛读样本

- **S1 Self-Consistency：标题与摘要的中心统一。**标题呈现清楚的动作与结果，摘要围绕同一操作展开，接近结尾才集中列举量化表现。可学习“一个中心动作贯穿标题、摘要、引言”，减少同一概念的多套称呼。本轮只有摘要与身份筛读，不给逐节分析。[作者摘要](https://arxiv.org/abs/2203.11171)；[官方接收页](https://iclr.cc/virtual/2023/poster/11718)。
- **S5 GraphRouter：摘要句子分工明确。**开头说明实际选择情境，随后指出具体困难，再命名框架并解释其工作方式，最后给评价结果。当前稿可借用这种顺序，让每句话完成一个信息任务，避免同一句同时交代动机、定义和发现。[官方论文记录](https://proceedings.iclr.cc/paper_files/paper/2025/hash/41b6674c28a9b93ec8d22a53ca25bc3b-Abstract-Conference.html)；[Poster页](https://iclr.cc/virtual/2025/poster/28926)。
- **S7 Verification/RL：结果类型由动词提示。**摘要先列两条研究路径，再以证明、形式化、经验检验等不同动作带领读者。可学习在句首明确当前句子承担的是定义、分析还是观察，避免每句话都使用“show”。本轮阅读范围是官方摘要。[ICML记录](https://proceedings.mlr.press/v267/setlur25a.html)。
- **S8 Deep Ensembles：让抽象优点接上具体评价。**摘要将容易实现、并行性、调参需求等特点写成语法平行的短语，接着按评价场景说明结果，末句落到更大规模场景。可学习其短语节奏与由概括到实例的顺序。[正式记录](https://papers.nips.cc/paper/2017/hash/9ef2ed4b7fd2c810847ffa5fa85bce38-Abstract.html)；[评审元数据来源](https://papers.neurips.cc/paper_files/paper/2017/file/9ef2ed4b7fd2c810847ffa5fa85bce38-Reviews.html)。
- **S9 Hydra：用对称句降低理解成本。**引言和摘要先介绍两条思路，用相似长度和句法说明各自特点，再进入文章的中心对象。这种“先A、再B、再说明本文问题”的写法适合清楚呈现当前稿的两种执行分配方式；重点是句子组织与转场。[AAAI记录](https://ojs.aaai.org/index.php/AAAI/article/view/7565)；[原文](https://ojs.aaai.org/index.php/AAAI/article/download/7565/7426)。

## 4. 补充风格样本：与主会名单分列

| ID | 文献 | 核实身份 | 阅读用途 |
|---|---|---|---|
| X1 | Brown et al., Large Language Monkeys: Scaling Inference Compute with Repeated Sampling (2024) | 作者arXiv原稿；未核实主会接收 | 补充观察段落组织，不计入9篇主会 |
| X2 | Li et al., More Agents Is All You Need (2024) | TMLR 10/2024 | 期刊摘要的简洁性 |
| X3 | Chen et al., FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance (2024) | TMLR官方2024-12-22接收公告 | 摘要中的实际情境与双指标表达 |

**X1的风格观察：**§1先将叙述分成两个短问题，后续章节沿用同一组名称，减少读者重新建立概念的负担。§4/Fig.7把曲线变化和解释紧邻安排。可借鉴“早命名、少改名、在图后立即解释”的写法。[作者原稿](https://arxiv.org/html/2407.21787v1)。

**X2的风格观察：**摘要用少量句子依次交代观察、方法名称、变化因素和实验覆盖面，信息密度高。适合学习删去冗长背景后的摘要节奏。[TMLR论文](https://openreview.net/pdf?id=bgzUSZ8aeg)。

**X3的风格观察：**摘要从具体使用情境和成本差异切入，再进入方法与结果；性能和成本始终使用一致的关系表达。可学习在结果句中明确“在什么条件下，哪个量发生什么变化”。[官方接收公告](https://groups.google.com/g/tmlr-announce-weekly/c/wcAk_8urPr4)；[OpenReview条目](https://openreview.net/forum?id=cSimKw5p6R)。

## 5. 当前稿可采用的风格模板

以下是根据上述语言动作提出的原创编辑模板；沿用现稿研究定位、术语与已有结果。

1. **摘要六句分工。**第一句提出读者关心的问题；第二句交代具体比较；第三句用主动动词说明研究做了什么；第四句给最主要结果；第五句给解释性结果或selector结果；第六句点明这一发现帮助读者理解什么。每句只承担一个主要任务。
2. **引言四段推进。**第一段将读者带入实际选择；第二段收窄到本文的精确问题；第三段概述研究方式与关键观察；第四段用少量平行句概括读者将获得的认识。各段首句可独立连读，形成一条清楚的摘要。
3. **结果段四步。**主题句先给观察；第二句给图表位置与数字；第三句解释设置间的差异；最后一句承接下一项分析。已经执行的selector零收益同样用直接陈述，不以长背景或流程描述延迟结果。
4. **首图与caption。**图中对象采用一致形状和命名；面板顺序与正文提问顺序相同。caption第一句概括读图目的，随后按(a)(b)(c)说明；具体设置放在后半段。
5. **句子节奏。**技术长句之后接一个短解释句；比较对象使用平行结构；同一术语保持一致；减少连续的“We first / We then / We finally”，改用研究对象作主语，使读者注意结果本身。

可用的原创英文骨架：

- *Under [setting], [quantity A] changes by [value], while [quantity B] remains [observed state].*
- *Figure X summarizes the comparison; the following sections examine each component.*
- *This pattern is clearest in [setting], where [specific observation].*
- *The repeated measurements reveal [observation], as illustrated in Figure X.*
- *The selector produces [observed result] on [evaluation set] (Table X).*

模板中的括号必须以现稿内容替换。模仿对象是信息顺序、段落功能和语言节奏，表达应重新组织成本文自己的文字。

## 6. 阅读与元数据说明

检索主线为各文献标题与会议名称，身份追踪路径为官方proceedings、逐篇会场页和期刊公告。风格阅读位置已逐篇列出；本报告不依据二手解读推测文章写法。

四篇主会对应论文完成摘要、引言和指定结果/图表的风格精读；S6使用作者预印本。X1另作补充风格阅读，其余条目为摘要或引言筛读。引用量使用带日期的API快照，未取得者保留UNKNOWN。展示形式、引用量和评审分数是独立元数据，报告没有将它们互相替代。
