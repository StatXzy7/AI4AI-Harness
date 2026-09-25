# 2026-09-25 论文结构对齐

本轮依据用户粘贴的结构意见，直接重排英文主稿与中文参考稿。它接续此前的叙述修订，以当前工作区为起点，不回退既有修改。本轮为结构与文字编辑，不构成独立跨模型科学审稿。

## 正文

| 新位置 | 内容与段落功能 | 主要改动 |
| --- | --- | --- |
| 1 Introduction | 问题、歧义、研究顺序、主要发现 | 按单次现象、子集对照、选择与回放、BIRD 补充诊断预告正文 |
| 2 Related Work | 自动化设计、重复采样与集成、选择与资源配置 | 前移，以三个主题段落界定贡献 |
| 3 Problem Formulation | 覆盖、稳定任务交互、可用选择 | 保留定义和两成员恒等式，不增设框架术语 |
| 4 Experimental Design | 先对象，再控制，最后应用层比较 | 4.1 总体与设置；4.2 同代码与留出重复；4.3 冻结选择与等执行次数重放 |
| 5.1 Single-Run Coverage in Generated Populations | 建立待解释的现象 | 从旧 6.1 前移，保留 35 成员总体与 8 成员重复面板的区别 |
| 5.2 Positive Oracle Estimates from Identical Programs | 关键识别对照 | 原同代码结果紧接覆盖现象 |
| 5.3 Repeat Validation and Diagnostic Sensitivity | 持续性及可判定边界 | 均值、缺失门槛与功效在同一小节解释 |
| 5.4 Pre-Execution Selection and Oracle Replay | 可用性与执行资源比较 | 以两个明确的段落区分执行前策略和事后 oracle |
| 5.5 Supporting Analysis of Executed Behavior | BIRD 补充诊断 | 完整 MATH 证据链之后呈现；完整图和轨迹进入附录 |
| 6 Discussion and Limitations | 评估启示与外推限制 | 集中综合，不重复所有数字；具体未执行干预假说移至 BIRD 附录 |
| 7 Conclusion | 可准确转述的中心结论 | 独立成章，不引入新实验或术语 |

结果的推进顺序为：现象 → 控制 → 跨重复持续性 → 选择与资源比较 → 独立执行诊断。各节开头说明该节检验的问题，结尾承接下一项比较；不再出现 MATH → BIRD → MATH 的往返。

## 附录

| 新附录 | 内容来源与定位 |
| --- | --- |
| A Harness Generation, Program Inventory, and Data Splits | 原探索性 MATH 附录、主面板清单、模型版本；先提供正文所需对象信息 |
| B Same-Code Controls and Repeated-Execution Protocol | 原重复研究的采集协议、完整任务口径、缺失及续采记录 |
| C Statistical Analysis, Calibration, and Sensitivity | 判定规则、采集后分析修订、诊断定义、模拟校准、有限重复偏差与控制验证 |
| D Frozen Selector and Execution-Matched Replay | 新重复研究的冻结策略、比较器表、政策估计目标、执行预算和实际采集账目 |
| E BIRD Execution Traces and Supporting Analyses | 发现研究条件、源码与结果图、完整轨迹、人工控制、指纹、第二目标探查及未执行的干预假说 |
| F BIRD Admission-Policy Study | 准入设计、主要与析因结果、同核心分解、R2/R3、成本和独立门控控制 |
| G Provenance, Protocol Deviations, and Historical Analyses | 早期协议探查、生成来源缺口、提取审计、未完成获取、历史选择、旧档案重评分及隔离试运行 |

附录新增简短链接导航。Phase-I / Phase-II 仅作为历史研究标识保留，不再承担一级导航。新选择器的 100 开发／400 评估划分与旧档案的 80／320 划分在 A、D、G 明确分开。旧分析、不利结果、缺失记录及偏离没有删除。

同核心分解的标题与表格现在同页：英文 F.2／表 10 在第 23 页，中文 F.2／表 10 在第 28 页。附录图表按段落固定位置排版，并设置章节边界与局部分页保护，避免跨入下一研究的内容。

## 内容与产物验证

- 英文 `latexmk -pdf` 与中文 `latexmk -xelatex` 编译成功。
- 英文正文结束于第 8 页，全文 30 页；中文正文结束于第 9 页，全文 36 页。全文页数包含声明、参考文献和重排后的附录。
- 两版均保留原有 33 个引用键；原标签无丢失，无重复标签、未解析引用、缺字或 overfull box。
- 迁移前后附录的数值数学片段集合核对无遗漏；共享数值宏、结果表文件、参考文献库和主面板清单与本轮快照逐字节一致。
- UTF-8 检查通过，中文段落已通过 PDF 提取和页面渲染检查。中文保留已有的宋体 small-caps 字形回退。
- 所有页面已生成预览；正文衔接、选择与回放、BIRD 转场和同核心分解另作放大检查。
- 完整任务口径仍为克隆 2.09%、生成面板 2.38%；配对 D=-0.10%，342 个共同完整任务。稳定专长结论仍为 INSUFFICIENT_EVIDENCE；未增加实验或改变数值。

改写前快照及编译／检查记录：`tmp/structure_alignment_20260925_205611/`。机器检查结果为其中的 `validation.json`。当前入口仍为 `paper/latex/main.tex` 与 `paper/latex_zh/main.tex`；本轮未提交或推送 Git。
