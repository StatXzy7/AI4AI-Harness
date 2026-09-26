# 补充精读：问题表达、段落推进与图文组织

调研日期：2026-09-26。按用户明确的范围，本文件只研究写作风格，以用户人工复核后的研究定位为前提。原论文观察只覆盖注明的章节；未把摘要筛读写成全文精读。会议年份采用正式发表年，引用数据库可能按最早预印本年份记录。

## R1 — Rethinking the Value of Network Pruning

**ICLR 2019；正式作者版页眉已核实。** Semantic Scholar 当前记录为 1,699 次引用。作者仓库提及的 best paper 属 NIPS 2018 的 workshop，不能写成 ICLR 主会奖项。阅读：摘要、§1、§3–4、§7，Figs.1–2、Tables 1–4。[作者正式版](https://arxiv.org/pdf/1810.05270)；[引用记录](https://www.semanticscholar.org/paper/4a1004ecd34118116344633c7cdcc34493c423ee)。

原文观察：先解释通用流程，再明确该流程背后的两个信念，以随机初始化的小模型检验这些信念。§3分别定义等训练轮数 Scratch-E 和等计算量 Scratch-B；§4按剪枝类型组织实验；§7讨论保留下来的方法价值及例外。首图解释常规流程，第二图明确控制的结构类别。

写作迁移：优先学习“日常做法→背后的判断→简洁比较→结果含义”的推进方式。每段只完成一项动作，把研究对象和比较对象放在句子主干。引言先让读者看懂问题，方法细节稍后出现。标题提出的疑问在实验小节中逐步得到回答。

## R2 — The Lottery Ticket Hypothesis: Finding Sparse, Trainable Neural Networks

**ICLR 2019 Best Paper，官方奖项页核实；4,470 次引用。** 阅读：摘要、§1、Fig.1及明确假说的段落。[论文](https://arxiv.org/pdf/1803.03635)；[官方奖项](https://iclr.cc/Conferences/2019/Awards)；[引用记录](https://www.semanticscholar.org/paper/21937ecd9d66567184b83eca3d3e09eb4e6fbd60)。

原文观察：引言从“既然能剪小，为什么不直接训练小网络”这一张力进入；先用Fig.1比较随机稀疏子网与找到的子网，再陈述可以检验的假说。读者先理解经验矛盾，再遇到正式命名。

写作迁移：保留当前 programs/rolls 的鲜明张力，让简单例子出现在正式定义之前。借鉴其“为什么不直接做更简单的事”的问句节奏：一句问题、一个可视比较、一个明确回答。术语在读者已经理解现象后再引入，读起来更轻。

## R3 — Chain-of-Thought Prompting Elicits Reasoning in Large Language Models

**NeurIPS 2022 Main Conference；22,167 次引用。** 阅读：摘要、§1、§3.3–3.4、Figs.1/5/6。[正式论文](https://papers.nips.cc/paper/2022/file/9d5609613524ecf4f15af0f7b31abca4-Paper-Conference.pdf)；[正式记录](https://papers.neurips.cc/paper_files/paper/2022/hash/9d5609613524ecf4f15af0f7b31abca4-Abstract-Conference.html)；[引用记录](https://www.semanticscholar.org/paper/1b6e810ce0afd0dd093f789d2b2742d047e316d5)。

原文观察：Fig.1以同一道小题的输入/输出对照说明操作；§3.3把三个替代解释分别对应到 equation-only、额外计算、答案后推理的对照；§3.4再测试不同示例与作者写法。实验安排不断回答前一结果产生的新问题。

写作迁移：一个核心图只回答一个读者疑问。采用“刚得到的结果自然引出下一问题”的小节衔接；各个对照先用一两句解释动机，再放实验配置。Fig.1的输入/输出并排方式也提示：首图先帮读者认识对象，再承载较多数字。

## R4 — τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains

**ICLR 2025；1,238 次引用。** 阅读正式版摘要、§1、§3指标、§5.1–5.2、Figs.1/4/5。未核实oral或评分。[正式论文](https://proceedings.iclr.cc/paper_files/paper/2025/file/1b126cc38b8638e07bef37e7b2bb72bf-Paper-Conference.pdf)；[引用记录](https://www.semanticscholar.org/paper/70aa016c1f68fd5c0261f26ad20017b8307650af)。

原文观察：引言列出实际使用需要满足的条件，以具体交互场景把条件落地。§3区分“至少一次成功”的 pass@k 与“每次均成功”的 pass^k；Fig.4把这两个随重复次数变化的量同图展示；§5.2随后分析失败轨迹。

写作迁移：先用自然语言说明读者想知道什么，再引入指标。把容易混淆的量放在相邻图或同表中解释，比跨页追踪定义更顺畅。结果段采用“先总体、再分组、最后一个具体轨迹”的节奏，让定量与例子相互照应。

## R5 — C-Evolve: Consensus-based Evolution for Prompt Groups

**ICLR 2026；正式proceedings核实。** 本轮阅读正式摘要，打开全文定位；不计结构精读，不报未获取的引用量或评审分。[正式记录](https://proceedings.iclr.cc/paper_files/paper/2026/hash/3f1351a10a3f904e6f3845a94275a909-Abstract-Conference.html)；[正式PDF](https://proceedings.iclr.cc/paper_files/paper/2026/file/3f1351a10a3f904e6f3845a94275a909-Paper-Conference.pdf)。

原文摘要明确把 prompt group 的投票表现用于演化适应度，而不只优化单个prompt分数。它代表“直接为聚合后的效用优化群体”的路线。

写作迁移：摘要用一个核心对象贯穿方法与结果，避免每句话引入新的名字。其动机—设计—结果的顺序可以作为摘要简洁度参照；本条不提供逐节模仿建议，因为本轮只筛读摘要。

## 检索范围与计量证据

根任务检索包括：论文精确题名及 ICLR/NeurIPS 正式页、ICLR 2019 Awards、ICLR 2026 Orals、GEPA/DEI/C-Evolve/AstaBench、τ-bench；从会议页继续打开原论文与关键章节。另通过 Semantic Scholar Graph API 批量获取公开论文元数据。原始返回保存在 `bibliometrics/semantic_scholar_batch.json`、`semantic_scholar_batch2.json`，每次含检索时间和所用标识符。上述数字统一为2026-09-26快照，不能视为跨数据库统一总引用量。

OpenAlex初检显示同题不同记录及与Semantic Scholar明显不同的引用量，故不混加、不取两者最大值；最终表只使用一个数据库。第二次Semantic Scholar批量请求中的 `ARXIV:2003.08555` 实际返回量子物理论文，题名核对后明确排除，保留原始返回作为核查记录。
