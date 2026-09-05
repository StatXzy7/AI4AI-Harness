# 当前论文写作审计（2026-09-05）

**SCORE: 4/10 | VERDICT: not ready**

评价对象是当前论文及其提交准备度，不是项目潜力或录用概率。完整初稿已经存在；目前最重要的工作是同步有效证据、纠正主张、恢复正确构建，然后接入完整的 Phase-II 结果。

审计基准：HEAD `70b42fb`；采集完整性快照时间为 **2026-09-05 13:20:12 +08:00**。JSONL 正在增长，以下比例只代表该快照。检查了正文全部章节、附录、现有构建日志、11 页 PDF 的逐页渲染、合并协议、生成日志与采集身份键；抽查了最近邻文献和 ICLR 官方要求。未修改论文或实验实现，未启动实验，未计算 Phase-II accuracy、D−A 或显著性。

## 1. 已完成与未完成

| 项目 | 实际状态 | 对写作的意义 |
|---|---|---|
| 论文结构 | 摘要、8 个正文章节、5 个附录部分均已存在 | 可以直接修订，无须重新从提纲起步 |
| Phase-I 核心现象 | `fig_hero_data.json` 保存 12 个生成候选、66 对，代码相似度均值 0.1431、outcome agreement 0.9619、21 对完全一致 | 支持特定已测群体的描述性发现；这次没有重跑模型验证原始采集 |
| Phase-II 生成 | A–D 72/72 份命名匹配且可解析的生成日志，3 个 seed 各 24 份；18/18 个 A/D 配对存在；E 另计 1 份 | “seed 2 尚未生成”的状态文档已经过期；日志齐备不等于全部证据通过验收 |
| 主矩阵 A/D | 95,812 / 205,744 唯一期望单元，46.57%；176 个选项含 bare × 1,169 题 | 尚不能写确认性效果结论 |
| B/C 核心矩阵 | 29,884 / 84,800 唯一期望单元，35.24%；212 个选项含 bare × 400 题 | 四臂因子效应尚未完整 |
| 排版文件 | 当前 PDF 共 11 页；`endofmain` 位于第 9 页 | 参考文献缺失，不能据此视为提交版通过 |
| 匿名与 AI 声明 | 2027 样式已使用；finalcopy 已关闭；AI use statement 已加入 | 有实际进展，但声明内容仍需与证据及作者实际贡献相符 |
| 图 | `paper/figures` 已有现象图和设计图，另有早期图 | 主文输入文件没有任何 `includegraphics`，图尚未接入 |

采集计数按 manifest 与 split 中的身份键计算，排除了重复行。快照中 A/D 有 2,610 条额外重复键，随后核查均来自 bare，涉及跨 shard 的 870 个重复身份键；这本身不证明结果冲突。本次未比较正确率值。详细文件大小与已读前缀 SHA-256 见同目录 `WRITING_AUDIT_COLLECTION_20260905.json`。

## 2. 阻塞提交的发现

### P0-1：论文继续使用协议已撤回的关键证据

正文仍以 Qwen/DeepSeek 旧协议 40 个候选、780/780 对一致，论证“旧协议在每个 builder 上均塌缩”和完成 factorial：

- [Introduction](E:/projects/AI4AI-Harness/paper/latex/sec_intro.tex:48)
- [旧协议跨 builder 结论](E:/projects/AI4AI-Harness/paper/latex/sec_protocols.tex:129)

但 [权威协议 §9](E:/projects/AI4AI-Harness/PHASE2_PROTOCOL.md:189) 已确认这些候选是 `SHA256 = bare` 的 M0 generation null，并明确撤回 builder-independent collapse 结论。相同源码产生相同 outcome 不能证明“句法不同却行为相同”，也不能据此归因 builder 或 gate。

**处理：**从摘要、引言、正文、附录和结论中移除这条支撑链。可把它作为 M0 生成失败报告；保留真正不同源代码的 Phase-I 现象，明确其适用群体。不要把 M0 藏起来，也不要继续将它计入 M1–M3 的有效机制比较。

### P0-2：正文的方法与当前研究设计已脱节

[权威协议 §1](E:/projects/AI4AI-Harness/PHASE2_PROTOCOL.md:22) 明确将所有 Phase-I 结果定为 discovery；Phase-II 是 6 builders × 3 seeds × 2×2（strategy forcing × conformance gate），主终点为 1,169 题上的配对 D−A headroom。正文仍以 151 题、两个嵌套对比、C/D admitted 为主轴，关键章节没有 Phase-II 说明。

A/B/C/D 的命名尤其危险：Phase-I 的 B/C/D 主要区分 builder；Phase-II 的 A/B/C/D 区分两个干预因子。如果直接往原表追加新结果，同名条件会代表不同实验。

**处理：**把 Phase-I 明确写为发现与诊断，单独定义 Phase-II 四臂；旧条件采用带阶段前缀的命名。现在即可写完 Phase-II 方法、统计分析计划与空表结构，结果待完整采集后回填。主结论基于连续效果及其不确定性，不以是否跨过 5 pp 代替处理效应比较。

### P0-3：最新 PDF 是带错误产物，不能提交

- [main.tex:88](E:/projects/AI4AI-Harness/paper/latex/main.tex:88) 调用 `iclr2026_conference` bibliography 样式，当前目录只有 2027 的 `.bst`。
- [main.blg:4](E:/projects/AI4AI-Harness/paper/latex/main.blg:4) 明确报找不到该样式；`main.bbl` 为 0 字节。
- [main.log:463](E:/projects/AI4AI-Harness/paper/latex/main.log:463) 起有 16 个未解析引用。实际 PDF 第 3 页显示 `(?)`，全稿没有参考文献列表。
- [main.log:551](E:/projects/AI4AI-Harness/paper/latex/main.log:551) 和 569 行报 `No counter 'none' defined`，对应两张 `longtable` 前的 `LTcaptype{none}`。

**处理：**统一 2027 样式，修复表格计数与 caption，完成 LaTeX→BibTeX→LaTeX→LaTeX 的干净构建。验收看退出码、日志和实际 PDF，不能只看“PDF 已生成”。现有审稿记录的 8.4/10 / almost 对应旧状态，不能继承为当前放行依据。

## 3. 会削弱科学论证的写作问题

### P1-1：headroom 的数学描述错误，checklist 被写成必要定理

[正文 §6.3](E:/projects/AI4AI-Harness/paper/latex/sec_protocols.tex:120) 写 oracle headroom 随 K 增长是定义保证的。实际定义为：

`H(P) = oracle_accuracy(P ∪ {bare}) − best_fixed_accuracy(P ∪ {bare})`。

反例：两个 harness 分别答对互补的半数题，oracle=100%、best-fixed=50%，headroom=50 pp；加入一个全部答对的 harness 后，oracle=100%、best-fixed=100%，headroom=0。单调的是 oracle accuracy，不是二者的差。

[Discussion](E:/projects/AI4AI-Harness/paper/latex/sec_discussion.tex:4) 还说未通过 checklist 的 router 至多找回最佳固定 harness。这也不成立：headroom 为 4 pp 的群体未达到 5 pp 阈值，仍可能支持优于固定选项的 routing。

**处理：**保留 matched-K 敏感性分析，但更正数学理由；区分“存在正的 oracle headroom”这一必要空间条件与人为设定的操作阈值。不能用阈值失败推出不可路由。

### P1-2：机制门禁、预算和因果措辞强于已记录过程

[Setup](E:/projects/AI4AI-Harness/paper/latex/sec_setup.tex:52) 写 free-form 额外通过 execution-path gate；[方法开头](E:/projects/AI4AI-Harness/paper/latex/sec_protocols.tex:11) 写所有群体 identical budget。但 [附录 D](E:/projects/AI4AI-Harness/paper/latex/sec_appendix.tex:94) 承认早期 C/D 生成工具与 per-attempt 日志未保留、smoke 在评估时执行；同段还同时写 3 retries 与 single-shot/no retry。无法据此把 Phase-I 描述为已经实现严格等预算、机制门禁的因果实验。

此外，“gate without a capable builder produces nothing”与正文 GLM B3 接受 3 个策略且有 headroom 相矛盾；“generation side fails”“task memorization”“deployment-relevant success”等需要限定到已测 pipeline、baseline 和 split。特别是任务重叠条件下的 +6.9 pp、零观测 harm，不是新任务部署效果或零风险保证。

**处理：**Phase-I 如实交代记录缺口；将严格干预定义放在真正执行该过程的 Phase-II。D−A 首先是 forcing+gate 组合效应；gate 主效应及交互必须由同一 400 题上的四臂分析支持。把 routing 负结果压缩为所测试 predictor 的边界结果，不推广成不可学习结论。

### P1-3：新颖性论证需要具体比较

当前 Related Work 已列出近邻，但反复用“none measures”“first systematic”完成排除。此次公开摘要抽查确认 [HarnessLens](https://arxiv.org/abs/2608.27311) 已采用行为相关任务和 attributable-evidence gate；[HarnessBank](https://arxiv.org/abs/2607.13683) 已讨论 search collapse、语义多样性库和 gated screening。这不否定本项目，但说明“使用行为门禁”本身不足以承担新颖性。

**处理：**把贡献落到 population outcome matrix 的测量、机制校准、独立数据库上的配对干预效果与生成失败率。为最近邻补一张短对照表：研究单位、是否测量 population outcomes、如何定义 diversity、如何校准 gate、验证设计。这里仅完成部分摘要核查，未完成系统新颖性排除，不能据此认证“首个”。BIRD 的 bib 条目存在，但 setup 未实际引用；a-evolve/Meta-Harness 等提及也需核对对应引用。

### P1-4：结果入稿前仍需数据验收

主矩阵未齐。协议 D13 记录修复缓存并保留既有 JSONL，不能仅凭重启断言既有单元均满足修复后的缓存语义。应交代保留数据的来源、重复记录处理与 R2/R3 对缓存效应的验证。当前看到审计 runner，未见对应完成的结果目录。

现有分析脚本 [analysis_primary.py:14](E:/projects/AI4AI-Harness/experiment/phase2/analysis_primary.py:14) 文档写 last-write-wins，但 [实现第 54 行](E:/projects/AI4AI-Harness/experiment/phase2/analysis_primary.py:54) 是 first-write-wins，且冲突检查只看 official_correct。这是可复现说明需修正的具体不一致；本次没有执行主分析或认定重复记录已损坏结果。

提交 `a04ac83` 的说明提到在 partial data 上验证分析管线，与当前冻结锚点“未计算 aggregate metric”的表述需要核对：究竟是合成/开发数据测试，还是实际 Phase-II 子集分析。提交标题本身不足以断言发生了结果窥视，应依据保存输出给出事实说明，不应事后改写冻结历史。

## 4. 阅读体验与制作问题

- 标题在最新 PDF 中换成五行，出现 `Diver-sity` 断词。建议先采用短标题，例如 *Behavioral Collapse in AI-Generated Harness Populations*；是否加入修复主张由最终 D−A 证据决定。
- 摘要约 302 个空白分隔词，混入多个阶段、多个样本量、admission、generation yield、routing、abstention。建议压到约 180–220 词，这是编辑建议，不是会议强制字数要求。
- 主表横跨第 6–7 页，B 与 B3 重复；`Section 6.0b` 不存在；“Rows 7–9”与实际 completed-grid 行错位。图表需要编号、caption 与明确阶段。
- `Appendix E` 被当作机制规格入口，但规格实际在 Appendix D；Discussion/Conclusion 出现 7→7.1 与 8→8.1 的重复标题；附录仍留 `pre-registration` 与 “two nested contrasts, originally two nested contrasts”。
- 两张新图尚未插入。旧 hero 数据对应 12 个候选/66 对；新现象图数据对应含 bare/react 的 14 个 harness/91 对、36 对一致、代码相似度约 0.1897。二者群体与计算口径不同，不能把新图直接配旧数而不解释。若报告 pair-level 相关系数的显著性，应考虑各 pair 共享 harness，避免把 91 对当作独立样本。
- `PAPER_PLAN.md` 仍有旧 GLM 0/6、旧 task split 与“剩余 LaTeX 化”等说明。`CURRENT_STATE.md`、`NEXT_STEPS.md`、`PHASE2_SUMMARY.md` 的阶段、时间、预算建议也互相冲突。应更新一个清晰的写作状态入口，旧状态标为历史快照，不能再当执行命令依据。

## 5. 推荐的下一步

1. **立即完成文稿同步与构建修复。**清除被撤回主张，补 Phase-I/II 边界，统一条件命名，修数学与引用，形成可正常阅读的完整修订稿。采集期间可以完成这些工作。
2. **把主论文压成一个问题。**“在固定原始生成预算下，明确策略加行为一致性门禁，是否提高群体相对最佳固定选项的可路由空间？”Phase-I 提出现象，Phase-II 回答问题；生成接受率用于解释可靠性，不能替代群体质量。
3. **最小主图表：**现象图、2×2 设计图、D−A 效果/各 builder×seed 分布图；主表报告 H(A)、H(D)、配对差、95% CI 与检验，副表报告 yield、四臂因子效应。IR、早期 completed-grid、LOHO 大部分移入附录。
4. **收齐后一次性完成冻结分析。**先验收 manifest、缺失、重复/冲突、哈希与分析代码对协议的实现，再回填数值。主对比保留 K=0 的全部预定 cell；四臂只比较相同 core 题目；按协议报告层级 bootstrap、paired permutation、Holm 校正及敏感性。
5. **冻结主线后再决定扩展。**不要依据旧预算文档把 SWE-bench、更多 target、Arm E 全矩阵都变成当前投稿前置条件。已有冻结的次要分析如未完成须如实记录，不能因结果不理想而静默移除。

建议时间：9 月 5–7 日完成修订骨架和正确构建；完整矩阵验收后 24–48 小时内产出主表与 Results；争取 9 月 12 日形成首个可提交版本，9 月 15–17 日完成独立复审与真实摘要。此为工作建议，不是采集完成时间保证。

官方截止：摘要 **2026-09-18 23:59 AoE**（北京时间 **9 月 19 日 19:59**）；全文 **9 月 25 日 23:59 AoE**（北京时间 **9 月 26 日 19:59**）。[ICLR 官方 CFP](https://www.iclr.cc/Conferences/2027/CallForPapers)

投稿正文上限 9 页，参考文献与 AI use statement 不计入；摘要截止后不能新增作者。已加入 AI 声明是正向进展，但其中“所有定量主张均由脚本产生”“核心决定均由人类作出”等必须由实际证据及作者本人核实。[ICLR 作者指南](https://iclr.cc/Conferences/2027/AuthorGuidelines)

## 6. 本轮验收结论

保留项目方向，暂不放行当前论文。重新验收需同时看到：已撤回主张清零、Phase-I/II 对齐、关键数学表述正确、完整且可追溯的主结果、无引用/LaTeX 错误的实际 PDF、图表与数字一致，以及基于该版本的独立跨模型审查。

下一轮执行提示词见 [ZCODE_WRITING_PROMPTS_20260905.md](E:/projects/AI4AI-Harness/review-stage/ZCODE_WRITING_PROMPTS_20260905.md)。
