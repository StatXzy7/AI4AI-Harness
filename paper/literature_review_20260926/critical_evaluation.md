# 顶会实证研究论文的写作风格调研

检索日期：2026-09-26。样本：12 篇正式接收的会议论文，覆盖 2019–2026；6 篇做结构细读，另 6 篇做针对性阅读（HAL 仅核 venue 与摘要）。本轮按用户最新要求只研究写法与风格，不据内容作相似性或新颖性判断，不改变当前论文的研究定位。来源与查询日志见同目录 `critical_evaluation_sources.json`。

## 推荐采用的写作风格

这些优秀论文共同采用的写法是：用一个短而具体的问题开场，很快让读者看到关键比较，再按照读者会产生的疑问组织证据。技术定义服务于叙述；每幅图有一个明确的阅读目的；摘要、引言和结果节保持同一条主线，却不重复同一段话。

最适合优先学习的组合是：**Min et al.** 的第一页与摘要节奏，**Engstrom et al.** 的对照说明，**Taori et al.** 的概念图与定义衔接，**Agarwal et al.** 的实证段落与图注，**Recht et al.** 的结果解释与结尾，**AstaBench** 的新近 agent 论文篇幅组织。这里的选择依据是表达方式，不是认定研究内容相同。

## 样本与质量证据

“正式接收”“获奖”“公开审稿意见”和“引用量”分别记录。日期化引用量由总报告及 `bibliometrics/semantic_scholar_batch.json` 统一记录；没有完整评分向量时，不由 oral、poster 或 award 推算平均评分。

| ID | 文献 | 正式来源 | 已核实的额外信号 | 阅读用途 |
|---|---|---|---|---|
| C01 | Agarwal et al., *Deep Reinforcement Learning at the Edge of the Statistical Precipice* | [NeurIPS 2021](https://proceedings.neurips.cc/paper/2021/hash/f514cec81cb148559cf475e7426eed5e-Abstract.html) | 官方 Outstanding Paper Award | 结构细读：实证段落、图注、推荐表 |
| C02 | Engstrom et al., *Implementation Matters in Deep RL: A Case Study on PPO and TRPO* | [ICLR 2020 官方页面](https://iclr.cc/virtual_2020/poster_r1etN1rtPB.html) | 评分未核实 | 结构细读：对照表与小节串联 |
| C03 | Ferrari Dacrema et al., *Are We Really Making Much Progress? A Worrying Analysis of Recent Neural Recommendation Approaches* | [RecSys 2019 accepted list](https://recsys.acm.org/recsys19/accepted-contributions/) | [官方 Best Long Paper](https://recsys.acm.org/best-papers/) | 针对性全文阅读：方法交代与讨论分层 |
| C04 | Chen et al., *A Closer Look at Few-shot Classification* | [ICLR 2019 官方目录](https://iclr.cc/Downloads/2019)；[正文页眉](https://arxiv.org/pdf/1904.04232) | 评分未核实 | 针对性全文阅读：清晰方法图、读表顺序 |
| C05 | Recht et al., *Do ImageNet Classifiers Generalize to ImageNet?* | [ICML 2019 / PMLR](https://proceedings.mlr.press/v97/recht19a.html) | 不填未核实奖项或分数 | 结构细读：双重观察、讨论回扣 |
| C06 | Taori et al., *Measuring Robustness to Natural Distribution Shifts in Image Classification* | [NeurIPS 2020](https://proceedings.neurips.cc/paper/2020/hash/d8330f857a17c53d217014ee776bfd50-Abstract.html) | [公开 reviews](https://proceedings.neurips.cc/paper/2020/file/d8330f857a17c53d217014ee776bfd50-Review.html) | 结构细读：概念图、定义、小节组织 |
| C07 | Min et al., *Rethinking the Role of Demonstrations: What Makes In-Context Learning Work?* | [EMNLP 2022 main](https://aclanthology.org/2022.emnlp-main.759/) | 不填未核实奖项或分数 | 结构细读：摘要与第一页节奏 |
| C08 | Turpin et al., *Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting* | [NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/ed3fea9033a80fea1376299fa7863f4a-Abstract-Conference.html) | 不填未核实奖项或分数 | 针对性全文阅读：定量结果与例子的衔接 |
| C09 | Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* | [NeurIPS 2025 Datasets and Benchmarks](https://papers.nips.cc/paper_files/paper/2025/hash/b1041e52d3be19f0a9bc491657488e4a-Abstract-Datasets_and_Benchmarks_Track.html) | 不填未核实奖项或分数 | 正式摘要及全文结构：平行贡献条目 |
| C10 | Yamada and Otani, *Does Robustness on ImageNet Transfer to Downstream Tasks?* | [CVPR 2022](https://openaccess.thecvf.com/content/CVPR2022/html/Yamada_Does_Robustness_on_ImageNet_Transfer_to_Downstream_Tasks_CVPR_2022_paper.html) | 不填未核实奖项或分数 | 摘要与 §3：实验设置的说明顺序 |
| C11 | Bragg et al., *AstaBench: Rigorous Benchmarking of AI Agents with a Scientific Research Suite* | [ICLR 2026 oral 官方目录](https://iclr.cc/virtual/2026/events/oral)；[正式正文](https://arxiv.org/pdf/2510.21652) | Oral 已核实；分数未核实 | 结构细读：新近 agent 论文的篇幅安排 |
| C12 | Kapoor et al., *Holistic Agent Leaderboard: The Missing Infrastructure for AI Agent Evaluation* | [ICLR 2026 官方目录](https://iclr.cc/virtual/2026/papers.html)；[作者研究组](https://sage.cs.princeton.edu/) | 不填未核实奖项或分数 | 仅摘要：三项贡献的平行表达 |

## 六篇结构细读：具体学什么

### C07：摘要直接给发现，第一页让读者看懂主要比较

**观察到的写法。** 摘要顺序是已有能力、待解释问题、关键观察、进一步分析、意义。第一页 Fig.1 只呈现三种条件；§4 先建立主结果，再用 Fig.4–6 回答读者可能提出的疑问；§5/Fig.7 才转入分因素分析。[全文](https://aclanthology.org/2022.emnlp-main.759.pdf)

**可采用的写作动作。** 当前稿摘要的第二句就进入核心问题，第三句说明关键比较，不先铺陈多个指标名称。首图只承担主比较；引言在指向首图后，用一句话交代后续分析将解释什么。每个结果小节的首句应让读者知道这一节接着回答哪个问题。

### C02：把对照条件集中说清，结果段落顺着问题推进

**观察到的写法。** Table 1 集中列各实验变体保留的成分；§3/Fig.1 展示第一层现象，§4/Fig.2 转向行为，§5/Table 2 回到性能解释。小节之间有明确的提问式过渡，避免把实验写成孤立清单。[ICLR 页面](https://iclr.cc/virtual_2020/poster_r1etN1rtPB.html)、[全文](https://arxiv.org/pdf/2005.12729)

**可采用的写作动作。** 将当前稿的比较条件放进一张简洁对照表，正文只讲差异为何与当节问题有关。结果小节采用“承接上节观察→本节比较→核心结果→下一问题”的四步顺序；术语固定后不反复换同义词。读者需要连续记住的是几个对象及其关系，而非实现细节列表。

### C06：先提供视觉直觉，再给精确定义

**观察到的写法。** Fig.1 用左右面板依次解释概念和呈现实际结果；§2 在图示之后给出定义，§4 则按情境分组报告。引言的要点以完整陈述句表达，使结论容易扫描。[全文](https://proceedings.neurips.cc/paper_files/paper/2020/file/d8330f857a17c53d217014ee776bfd50-Paper.pdf)

**可采用的写作动作。** 对当前稿容易混淆的量，先用一幅小图或一个具体例子建立关系，再给符号。每个定义后只保留一句“这个量回答什么问题”。图中沿用正文同样的对象名称、颜色与顺序。主结果按科学问题分组，避免按分析脚本名称或完成时间排列。

### C01：结果先行的段首，信息完整而不冗长的图注

**观察到的写法。** §3 用清楚的段首陈述组织 case study；Fig.2 和 Fig.5 的 caption 明确说明比较对象、如何读图和看到的现象。Table 1 把报告问题与建议并排，§4、§5 分别展开方法与应用；长篇细节被分配到附录。[全文](https://proceedings.neurips.cc/paper/2021/file/f514cec81cb148559cf475e7426eed5e-Paper.pdf)

**可采用的写作动作。** 结果段首直接写本段观察；第二句交代比较与数值，第三句给解释。图注按“面板内容→统计表示→主要读法”排列。主文只保留帮助理解比较的定义与设置；复现细节集中整理到附录，用精确引用承接，不让每个段落都被程序说明打断。

### C05：把两个看似不同方向的观察放在同一条叙述里

**观察到的写法。** 摘要并列给出两项相互补充的发现；Fig.1 同时承载两种观察。§2 预先组织解释，§3、§4 再给方法与结果；§5 回到前面的问题，使讨论具有明确回扣，而非另起一篇短文。[全文](https://proceedings.mlr.press/v97/recht19a/recht19a.pdf)

**可采用的写作动作。** 当前稿如果需要呈现多个层面的结果，应先给一个总观察，再逐层说明它们如何共同回答中心问题。讨论节按引言提出的问题顺序回应；结尾用简短段落指出本文让读者理解了什么，以及下一步最值得理解什么，不逐条重复结果表。

### C11：新近 agent 论文的模块化呈现与结果阅读路线

**观察到的写法。** 引言用平行结构列研究动机；Fig.1 给整体关系，Table 1、Table 2 分别负责定位与设置。§4.2 集中说明评价口径，§5/Fig.2 用同一坐标格式分组展示结果。正文保留整体阅读路线，细分结果放附录。[全文](https://arxiv.org/pdf/2510.21652)、[ICLR oral](https://iclr.cc/virtual/2026/events/oral)

**可采用的写作动作。** 当前稿可借鉴统一的图表语言与主次分配：总图固定对象关系，结果图沿用相同标签；总结果之后才进入分组解释。相关设置一次讲清，用短语回指。这个范本适合学习 agent 论文的组织节奏，不必复制其大规模 benchmark 的篇幅或贡献数量。

## 六篇补充样本的写作动作

| 文献 | 经原文核对的表达特点 | 可以怎样学习 |
|---|---|---|
| C03 RecSys progress | §2 说明材料与方法，§3 展示比较，§4 将讨论分成不同问题；Tables 8–9 的文字按读表顺序解释。[全文](https://arxiv.org/pdf/1907.06902) | 先让读者知道分析了什么，再解释结果；讨论拆成少量有明确目的的段落。 |
| C04 closer look | Fig.1 将流程画得简洁；§4.2/Table 1 先建立读者对实验实现的理解，再引导到主要结果。[全文](https://arxiv.org/pdf/1904.04232) | 用一张易读流程图减轻方法节负担；结果段明确指出读者应看哪一行或哪一列。 |
| C08 CoT faithfulness | §3.2 先给定量结果，§3.3 再用可读例子解释现象；例子沿用此前概念。[全文](https://proceedings.neurips.cc/paper_files/paper/2023/file/ed3fea9033a80fea1376299fa7863f4a-Paper-Conference.pdf) | 个案放在总体结果之后，用于帮助理解；避免在 introduction 中堆叠长 trace。 |
| C09 MAST | 正式摘要用平行动词组织数据、分析框架与验证流程，贡献条目彼此分工明确。[正式版](https://papers.nips.cc/paper_files/paper/2025/file/b1041e52d3be19f0a9bc491657488e4a-Paper-Datasets_and_Benchmarks_Track.pdf) | contribution bullets 保持相近长度与语法结构，每条只承担一种贡献类型。 |
| C10 robustness transfer | §3 先区分两种实验设置，再解释选择，随后给测量定义。[全文](https://openaccess.thecvf.com/content/CVPR2022/papers/Yamada_Does_Robustness_on_ImageNet_Transfer_to_Downstream_Tasks_CVPR_2022_paper.pdf) | 写设置时先交代“做什么”，再说明“为什么”，最后给参数和指标。 |
| C12 HAL | 摘要以三项平行贡献组织基础设施、系统分析与日志观察。[摘要](https://arxiv.org/abs/2510.11977) | 多贡献摘要可使用一致的句法，减少一口气塞入多个从句；每项都有具体产物或观察。 |

## 从公开评审中只提取可读性经验

C06 的 [公开 reviews](https://proceedings.neurips.cc/paper/2020/file/d8330f857a17c53d217014ee776bfd50-Review.html) 一方面肯定文章组织与可读性，另一方面指出正文信息密度过大，有些有价值内容容易淹没。可直接借鉴的编辑原则是：缩减同页同时引入的概念数量，让每个图表承担清楚的职责；把支撑主线的解释留在正文，把详尽列表放进附录。这里不沿用这些评论对研究充分性的判断。

评分信息单独保存于来源 JSON：Reviewer 2 在 rebuttal 后的文字明确出现 7，但完整评分向量未取得，因此不称该文平均 7 分或一致高分。

## 可用于后续写作的段落配方

以下是从阅读中归纳的编辑方法，不是代写文本，也不改变当前研究内容。

**摘要：五个句子角色。** 研究对象与具体问题；本文采用的关键比较；最重要的发现；解释这一发现的第二层结果；读者由此获得的认识。句子角色可以合并，但主发现应在摘要中部以前出现。

**引言：五个段落角色。** 从具体问题开始；解释为什么这个问题值得回答；介绍本文怎样回答；用易读语言概括发现；列出两到三项相互独立的贡献。背景引用服务于每段目的，不把引言写成发展史。

**结果段：四步。** 段首一句给观察；一句明确对象与设置；一至两句给数值、图表及解释；末句衔接下一个问题。不要把“我们接下来做了什么”作为所有段落的开头。

**图与图注。** 图标题表达阅读目的；caption 先解释面板与编码，再解释统计量，最后指出主要读法。颜色、对象顺序与命名跨图一致。正文应说明这张图为何出现在这里，不逐句复述 caption。

**讨论与结尾。** 按引言的问题回扣发现，集中解释最值得带走的一点。研究范围和下一步用一个紧凑段落交代，避免在每个结果段落末尾重复同一组限制。结尾应结束论证，不再引入新概念。

## 来源核实说明

- C02、C04 的 OpenReview 页面直开遇 browser challenge；接收由 ICLR 官方页面/目录及公开正文确认，评分仍未验证。
- C10 是 CVPR 2022；C06 是 NeurIPS 2020，两篇身份分别记录。
- C09 使用正式发表版本，避免将早期预印本的元数据混入来源记录。
- *Measuring Faithfulness in Chain-of-Thought Reasoning* 本轮未核得正式会议接收；*AI Agents That Matter* 已核为 TMLR 2025 期刊论文，均未计入这 12 篇会议样本。
- ICLR 2026 virtual 页面直开可能受 robots 限制；AstaBench oral 和 HAL 接收通过官方搜索索引及正式正文/作者网站交叉核对。HAL 未作结构精读。
