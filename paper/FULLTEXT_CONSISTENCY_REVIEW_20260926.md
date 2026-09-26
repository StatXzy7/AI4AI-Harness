# 当前全文完整性与叙述一致性复核（2026-09-26）

> 历史审核记录：以下问题随后已按用户授权完成修订，当前验收状态见[全文一致性修订验收](E:/projects/AI4AI-Harness/paper/FULLTEXT_CONVERGENCE_CLOSEOUT_20260926.md)。下文保留修改前的证据和评分。

**score 8/10；verdict: almost。评分针对文字完整性、叙述连贯性和全文一致性，不是录用概率或实验正确性评分。**

结论：主线已经收敛，正文与附录基本成稿，但不能说所有内容已经完全一致。剩余问题集中在三张沿用的附录图、差值单位、两处方法说明缺口和少量语义表述。无需重构全文；应完成一次定点收尾。

本次只读检查论文，新增本审核记录及临时核验材料；未修改论文、实验代码或实验数据，未运行实验或重算统计。没有将目录中未被入口引用的历史文件当作当前全文。

## 审核范围与版本

- 英文入口：[main.tex](E:/projects/AI4AI-Harness/paper/latex/main.tex)，当前 PDF 22 页，正文结论结束于第 8 页。
- 中文入口：[main.tex](E:/projects/AI4AI-Harness/paper/latex_zh/main.tex)，当前 PDF 26 页，正文结论结束于第 9 页。
- 逐节检查摘要、正文 1–7 节、声明、图表文字，以及实际纳入的附录 A–F；双语核对覆盖 24 对对应源文件。
- 每版均有 34 个活动 TeX 输入、33 个引用键。输入解析考虑了中文入口的共享英文表格搜索路径。
- 当前 PDF 晚于对应活动 TeX 源；已检查现有编译日志、交叉引用和 PDF 文本，并重新渲染两版所有页面查看缩略图，放大核对存在问题的附录图。没有重新编译或导出论文。
- 未发现活动输入缺失、未定义交叉引用、重复标签、未解析文献键、TODO/TBD/FIXME 或空结果占位。当前日志无 Overfull box；仍有 Underfull 提示及中文 small-caps 字形回退，未在预览中发现明显溢出或缺字。
- 机械记录：[英文核验](E:/projects/AI4AI-Harness/tmp/fulltext_review_20260926/latex_checks.json)、[中文核验](E:/projects/AI4AI-Harness/tmp/fulltext_review_20260926/latex_zh_checks.json)。记录活动源哈希及 PDF 哈希。本轮未再次核对外部参考文献元数据。

## 必须收尾的七项

### 1. 附录设计图与现文的研究边界不一致

定位：英文 PDF 第 19 页 Figure 3；[插图入口](E:/projects/AI4AI-Harness/paper/latex/sec_app_bird_admission.tex:21)。

图内仍写 `9 DBs never opened in development`，同页正文却披露 `18-item smoke-test exposure`。图内总标题把 `2×2 factorial + open-mechanism arm` 一起放在 `confirmatory design` 下，II-E 框仍写 `secondary`；图外新增说明则写 `development-only; excluded from confirmatory comparisons`。

这是图内旧文本与新正文未同步，不是需要重新讨论实验。应直接修改嵌入图的总标题、II-E 身份及数据库暴露说明；仅在图下加一句说明没有消除图内歧义。中英文共用该图，需共同验收。

### 2. 附录仍有百分数与百分点混用

正文已经规定 accuracy 用 `%`、gains/headroom 用 `pp`，但以下活动内容仍沿用旧单位：

- [分解表第 3 行](E:/projects/AI4AI-Harness/paper/latex/revision_decomposition_table.tex:3)：`H (%)`，对应英文 Table 11。
- [敏感性表第 3 行](E:/projects/AI4AI-Harness/paper/latex/revision_sensitivity_table.tex:3)：`Estimate (%)`、`95% CI (%)`，对应 Table 12。
- 英文 PDF 第 20 页 Figure 4 的两条图轴仍写 `headroom (%, absolute difference)`，而[图注](E:/projects/AI4AI-Harness/paper/latex/sec_app_admission.tex:33)声称图轴使用 percentage points。

把差值表头和图轴统一为 `pp`；准确率、覆盖率和错误率保留 `%`。无需修改任何数值。

### 3. 现象图标题仍是旧版的更强结论

定位：英文 PDF 第 17 页 Figure 2；[插图及当前图注](E:/projects/AI4AI-Harness/paper/latex/sec_app_bird_traces.tex:22)。

图内标题仍为 `Syntactically diverse, behaviorally collapsed`，并保留 `day-1 population`。现文已经准确地写成有限任务上的 `observed correctness` / `correctness vectors`，图注也说明并非程序等价检验。图标题中的整体行为判断比测量对象更宽，且内部时间代号没有必要。

建议图内标题直接与当前图注统一，例如 `Source differences and observed correctness`；删除 `day-1`。这属于统一已有论述，不是增加限定或改变结果。

### 4. 讨论把“影响行为”与“产生有效结果”混在一起

定位：[英文讨论第 11 行](E:/projects/AI4AI-Harness/paper/latex/sec_discussion.tex:11)及中文对应段。

原句把 implementation、activation、valid final output 写成机制 `affect behavior` 的必要条件。但[正文 T3](E:/projects/AI4AI-Harness/paper/latex/sec_supporting.tex:28)恰好展示机制已运行、返回无效 SQL、造成得分下降。无效输出同样改变行为。

最小修订：将句尾改为产生可用任务优势所需的路径，例如 `to yield a usable task advantage`，或直接说这是从实现、激活到有效输出的三个检查环节。同步检查 supporting 段末尾的同类概括。

### 5. 选择器训练目标仍缺一个定义

定位：[英文附录 D 第 6 行](E:/projects/AI4AI-Harness/paper/latex/sec_app_selection.tex:6)、[中文对应段](E:/projects/AI4AI-Harness/paper/latex_zh/sec_app_selection.tex:5)。

文中已经写出 multinomial-logistic 输入、成员的 available-repeat mean、五折概率平均、推断并列规则和 0.15 回退阈值，但没有说明如何把各成员开发集均分转成分类训练标签，以及训练标签并列时怎么处理。

因此，训练与推断之间仍缺一环。需依据实际已用方法补上标签构造与训练并列规则；不能凭常见做法假设为 argmax，也不能把推断阶段的并列规则自动当作训练规则。若实际固定超参数对复现有影响，可一并明确。此项需要查明既有方法事实，无需新增实验。

### 6. 校准表没有把比较规则解释完整

定位：[统计附录的三折定义](E:/projects/AI4AI-Harness/paper/latex/sec_app_statistics.tex:5)、[多重复校准段](E:/projects/AI4AI-Harness/paper/latex/sec_app_statistics.tex:71)、[校准表表头](E:/projects/AI4AI-Harness/paper/latex/calibration_table.tex:8)。

目前只定义了“两次发现重复、第三次验证”的三折规则，后面却报告 R=5、10、20 的功效；这些设置的发现/验证划分未说明。表中 `plug` 的正向判定规则或阈值也没有定义，读者不能从描述性 plug-in 估计直接知道为何该列对应 false-support/power。

应补齐 R>3 的实际划分规则、`plug` 的判据，并给代表性的 17.5 pp 双专家场景提供概率设置或精确定位。这里只指出论文说明未写全，不评价实现是否正确，不要求补跑。

### 7. 校准表注的“支持零假设”容易把含义读反

定位：[英文表注第 97 行](E:/projects/AI4AI-Harness/paper/latex/sec_app_statistics.tex:97)、[中文表注第 36 行](E:/projects/AI4AI-Harness/paper/latex_zh/sec_app_statistics.tex:36)。

英文 `rarely supports nulls` 被译成“很少支持零假设”。该表报告的是零假设成立时错误宣告存在互补性的比例，不是接受零假设的频率。

建议同步改为 `rarely gives false support under the null`／“在零假设成立时很少错误给出正向支持”。

## 其余语言收尾项

以下不改变主线，不应据此要求重写全文或补实验。

|位置|问题|最小处理|
|---|---|---|
|[setup:73](E:/projects/AI4AI-Harness/paper/latex/sec_setup.tex:73)、[supporting:35](E:/projects/AI4AI-Harness/paper/latex/sec_supporting.tex:35)|先写 assigned strategies，结果改称 forced|首次写 assigned-strategy (forced)，之后统一名称|
|[supporting:35](E:/projects/AI4AI-Harness/paper/latex/sec_supporting.tex:35)|admission 的 -0.16 pp 插入轨迹链后，结尾 Together 没有说明它与前文关系|补一句该准入比较在本节的作用，或把细节留在附录；无须重复整套区间|
|[statistics:41](E:/projects/AI4AI-Harness/paper/latex/sec_app_statistics.tex:41)|正文成功概率 p_h(x)，附录改成 q_h(x)|统一同一对象的符号|
|[bird traces:66](E:/projects/AI4AI-Harness/paper/latex/sec_app_bird_traces.tex:66)|宏展开后列出 single-call, react, single-call，两个对象重名|明确 baseline 与 single-call generated candidate|
|[bird traces:68](E:/projects/AI4AI-Harness/paper/latex/sec_app_bird_traces.tex:68)|Quoted SQL 全部 capped at 120 characters 的范围过宽，后文含完整 gold SQL|改成 Logged SQL excerpts，区分日志摘录与完整查询|
|[bird traces:82](E:/projects/AI4AI-Harness/paper/latex/sec_app_bird_traces.tex:82)|the two / respectively 在第二条 SQL 出现前使用|移到两条 SQL 后，明确 gold query 与 baseline query 的对应值|
|[bird admission:130](E:/projects/AI4AI-Harness/paper/latex/sec_app_bird_admission.tex:130)|format-guard 在解释 108 次失败时首次出现，所属策略不清楚|首次出现时说明其与 forced strategies 的关系|
|[中文 phase1:10](E:/projects/AI4AI-Harness/paper/latex_zh/sec_phase1.tex:10)、[中文 statistics:26](E:/projects/AI4AI-Harness/paper/latex_zh/sec_app_statistics.tex:26)|统计 plug-in 译为“插件”|统一为“代入估计（plug-in estimate）”|
|[中文 selection:19](E:/projects/AI4AI-Harness/paper/latex_zh/sec_app_selection.tex:19)|policy 在正文叫“策略”，附录叫“政策”|统一“选择策略”|
|[中文 bird traces:70](E:/projects/AI4AI-Harness/paper/latex_zh/sec_app_bird_traces.tex:70)|“修复提示导致输出契约失败”比英文 invites the failure 更像干预归因|改为“该修复提示下，输出契约再次失败”|
|[中文 admission:3](E:/projects/AI4AI-Harness/paper/latex_zh/sec_app_admission.tex:3)|“对结果前规格的校正重分析”生硬|改为“按照查看结果前制定的分析方案进行校正重分析”|
|[中文 selection design:5](E:/projects/AI4AI-Harness/paper/latex_zh/sec_selection_design.tex:5)|“所有均匀大小为 b 的子集”修饰关系错误|改为“从全部大小为 b 的子集中均匀抽取”|

摘要、引言、主图、讨论、结论仍重复同一组三项发现。这保证了方向一致，但讨论和结论可各少重复一轮数字，将篇幅用于解释。属于可选精简，不是当前未收敛的主要原因。附录 Figure 3 在现有尺寸下图内文字偏小，修改图文时可一并增大字号或占宽。

## 已经收敛的部分

- 主问题及证据顺序一致：覆盖增加 → 同代码控制 → 可重复差异及其方向 → 冻结选择与等执行次数重放。BIRD 的支撑地位明确。
- 摘要、正文、附录与中文的主要 MATH 数字一致：386 道共同题，八个生成程序加基线，九个同代码槽位，每个三次；生成与克隆 plug-in 2.33/2.16 pp，D=-0.26 pp，相关性 0.789/0.006，持续损失涉及 100 题、持续获胜涉及 1 题，选择收益 0.00 pp，27 次执行的覆盖均为 98.70%。
- 全体 35 个生成程序的单次覆盖 99.22% 与选定 repeat panel 的 98.70% 对应不同程序集合和执行方式，现文已区分，不是数字冲突。
- D 的显示值与两个已舍入 G 相减略有不同，表注已经解释；重放表也已说明先算差值再舍入。
- `Insufficient Evidence`、三次重复的功效边界、排除题与冲突敏感性均有明确位置。科学结论未决不等于稿件未写完。
- harness executions 与 model calls/tokens 已区分；没有把 execution-matched 偷换成 token-matched。
- 未发现结论级中英文错位。中文共享英文图表是入口明确规定的方式，本身不算未翻译完成。
- 匿名作者属于投稿模式；历史 unknown、未保存记录和 gate 局限有清楚语境，不应当成待办占位。

## 附录覆盖记录

|附录|逐节检查范围|状态|
|---|---|---|
|A|生成说明、程序清单、模型标识、数据划分、单次覆盖|基本完整，与正文数量口径一致|
|B|面板选择、完整性、排除题、冲突、重复性及格式例子|叙述已闭合|
|C|G/D 判定、总体目标、有限重复估计、校准表|校准定义和表注仍需收尾|
|D|选择器、策略表、S、执行次数重放与账目口径|训练标签定义仍缺失|
|E|discovery、手写控制、T1–T3、全部 worked examples、现象图|旧图标题与少量用语待同步|
|F|设计、主比较、factorial、分解、R2/R3、成本、准入与提取失败|旧图边界、图表单位待同步|

建议验收顺序：先同步三张图与共享表头，再补选择器和校准的既有方法定义，最后修语义与中文术语。完成后重新编译两版，按相同活动输入链检查一次即可；不需要再进行全文结构重写。
