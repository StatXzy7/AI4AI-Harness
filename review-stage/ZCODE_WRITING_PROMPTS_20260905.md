# ZCode 论文修订提示词

以下三段按阶段使用。第一段现在可执行；第二段仅在所需矩阵完整并完成数据验收后使用；第三段交给独立的 Codex 审核者。本文不授权新增付费实验或对外提交。

## 提示词一：现在执行的写作修复

你是本项目执行者 ZCode。请依据 `CLAUDE.md`、`PHASE2_PROTOCOL.md`、`PROTOCOL_FREEZE.txt` 和 `review-stage/WRITING_AUDIT_20260905.md`，直接修订当前论文，产出完整、可正确编译、与有效证据一致的版本。不要只给计划。

本轮修改论文、图表引用及写作状态文档；保留正在运行的采集和原始结果，不启动新增付费实验，不改冻结 estimand/split/gate/排除规则，不执行未完成 Phase-II 的效果分析，不修改 `CLAUDE.md`。你与其他任务共享工作区，不覆盖别人或运行进程正在写入的文件。

按以下顺序完成：

1. 建立紧凑的 claim→证据→论文位置清单，标注 supported / discovery-only / pending / retracted。优先核对摘要和结论的每个数值与因果句。
2. 全文移除以 40 个 bare 源码副本、780/780 相同 outcome 证明 builder-independent behavioral collapse 的论证。将其如实重分类为 M0 generation null。只对真正不同源码群体保留 syntactic-versus-outcome 现象。
3. 将 151 题旧实验清楚标为 Phase-I discovery；新增 Phase-II 方法：6 builders × 3 seeds，strategy forcing × conformance gate 的 A/B/C/D 四臂，主 D−A 在 1,169 题上配对，因子次要分析在相同 core-400 上。给两个阶段的同名条件加明确前缀，避免 B/C/D 一名两义。
4. 保留 Phase-I 的实测结果和记录缺口。不得把旧 smoke check 写成已经执行严格 conformance gate，不得为没有日志的运行声称等预算。D−A 只代表组合干预，gate 单独作用与交互等完整四臂结果再下结论。
5. 更正“headroom 随 K 必然增长”和“未过 5 pp checklist 就无法优于最佳固定 harness”。区分 oracle accuracy 与 headroom；阈值为操作描述，主科学比较使用连续效果与 CI。把 routing 负结果限定在已测试模型与划分，删除零观测 harm 等于部署保证的暗示。
6. 主文组织为问题→测量与诊断→Phase-II 设计→完整结果→边界。收齐前 Results 使用清楚的 pending 占位，禁止把 Phase-I 或 partial-data 数字填成 Phase-II 结果。不要让等待采集阻止方法、结构、引用和语言修订。
7. 将摘要压到约 180–220 词，缩短标题；以现象测量和受控协议比较为主线，IR、旧 completed-grid 和大部分 LOHO 放附录。准备正向、无显著差异、反向三种结果对应的条件式结论草案，最终按冻结分析选择，不改研究问题迎合结果。
8. 接入现象图和研究设计图。统一 12 候选/66 对与含 baseline 的 14 harness/91 对的口径，检查图注、正文、数据文件一致。每幅图有 caption、样本量、阶段和可追溯来源。不能把 pair 当独立样本草率解释相关性 p 值。
9. 修复 bibliography 为匹配的 2027 样式及 `LTcaptype{none}` 错误；修正虚构的 Section 6.0b、错误附录引用、B/B3 重复行、行号说明和重复小节标题。给 BIRD 与文中提及的工作补齐实际引用。核对最近邻原文，以具体差别支持新颖性，不依赖“none/first”的笼统排除。
10. 在独立 build 目录干净编译；检查退出码、非空参考文献、零 undefined citation/reference、零 LaTeX error、正文≤9页，并逐页检查实际 PDF。AI use statement 的人类贡献事实由作者核实，Agent 不代作保证。
11. 更新 `paper/PAPER_PLAN.md`，把过期状态文档标为历史并指向有效入口；不要重写冻结时的历史状态。最终交付修订 tex/PDF、精简 claim-evidence 清单、已修与待数据问题列表及构建证据。

把最新版本送给不同模型的 Codex 独立复审，明确版本/文件哈希；不得用旧的 8.4/10 记录作为本版通过依据，也不要自审代替独立审核。

## 提示词二：完整采集后的结果入稿

请先只做完整性验收，确认 `PHASE2_PROTOCOL.md` 所需 18 个 A/D 配对在 1,169 题上的唯一单元、四臂在相同 core-400 上的单元全部齐备，并核对生成日志、manifest、目标模型、harness 哈希与正确判分字段。分开报告缺失、重复和冲突，不以 JSONL 行数或文件大小宣称完成。若未齐，保持 pending，完成其他写作工作；不运行 `--allow-partial` 生成论文结论。

特别核对 bare 的重复身份键、first/last-write 规则、D13 前后保留记录的来源及缓存敏感性。查明此前 “partial data 验证分析管线”使用了什么数据；若读过真实 Phase-II 聚合结果，按事实记录时间和用途，不重新包装为从未分析。不要输出凭据或私密配置。

随后对分析实现做跨模型独立验收，确认与冻结协议相同：全部预定 builder×seed cell（含 K=0）；bare-inclusive headroom；D−A 总效应；数据库/题目/配对 cell 层级 bootstrap 10,000 次；配对 permutation；同一 core 上的四臂主效应与交互及 Holm 校正；K-matched 仅为敏感性。不得静默删去失败 cell、未完成次要分析或不理想结果。

验收通过后执行冻结分析并记录输入/输出哈希。先生成主表与图，再写 Results，最后改摘要、引言、讨论和结论。结果无论正向、接近零或反向均如实报告，不调整阈值、样本范围或主终点追求更好叙事。由证据决定“组合协议改善”“未发现稳定改善”或“改善了某项可靠性但未增加 headroom”等准确结论。

交付：完整性与偏差说明、冻结主表及分 builder×seed 结果、效应及不确定性图、所有正文数值的来源清单、可重建 PDF。对未完成的冻结次要研究明确标注，不将额外 SWE-bench/target/Arm E 研究作为本轮无限扩张任务。

## 提示词三：交给 Codex 的独立验收

你是审核者 Codex，不替执行者大范围改写实现。请审计本次指定 commit 和最新 PDF，按 `SCORE: x/10 | VERDICT: ready/almost/not ready` 输出，先列阻塞问题及文件行号/数据依据，不继承历史审稿分数。

检查：

1. 摘要、引言和结论是否仍有被撤回证据、Phase-I/II 混淆、5 pp 阈值冒充理论必要条件、headroom 单调性错误或超出实际 split 的 routing/部署主张。
2. Phase-II 每个关键数值能否从已冻结且完整的数据重现；是否包含所有预定 cell；D−A 与因子效应是否用了协议规定的同一题集与统计层级；重复/冲突/缓存偏差是否有真实处理证据。
3. 图、主表、正文和附录是否一致；机制门禁、生成预算、模型身份、评价器与开发暴露描述是否符合实际记录。
4. 最接近工作的比较是否支持贡献边界；是否把单域测量或某个 predictor 失败推广为普遍结论。
5. 最新 PDF 的参考文献、匿名、AI use statement、主文页数、实际排版及构建退出码是否通过。

区分已证实错误、合理未决疑点和可选增强；不把更多实验越堆越多作为默认建议。只有当前版本真正满足验收条件才能放行。
