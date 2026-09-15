# 诊断流程方法与验证计划（v1.3 = FROZEN v1.0，2026-09-15）

状态：v1.0 经独立审核（gpt-6-astra/xhigh）判 not ready（12 条）；v1.1 复核 6/10（11/12 解决+2 新阻断）；v1.2 复核仅剩分母可审计性一项（其余全部通过）；本版按审核者给出的规范做最后定义性修订（§5），随后冻结。第 3 轮修订预算用满；冷启动终审将全新检验。冻结范围仅限本轮新增分析，不追认为历史实验的预注册。

## 1. 研究对象

AI 自动生成的评估 harness 群体（MATH-500 存档 36 成员 × 400 任务；BIRD phase2 存档 18 cells）。产出五类命题 A–E 的状态判定 + 经验证的诊断流程 + 真实存档上的评估决策变化记录。

## 2. 定义（冻结口径）

- 执行条件 c = (solver_model, cache_state, repeat_index_policy, timeout, judge_version) 的显式元组。Y[h, x, r, c] ∈ {0,1}：成员 h 在任务 x 第 r 次重复、条件 c 下是否判对。**重复的定义**：仅当 (h, x) 相同且 c 中所有字段完全匹配的记录才构成同条件重复；任何字段不同→不同条件，不合并。
- 群体与规模：`K_raw` = manifest 中生成成员数（含失效/缺失，单独列出）；`K_unique` = 按规范化源码哈希去重后的成员数；population size = K_raw + 1（bare 参考）。成员身份键 = (manifest 成员名, 规范化源码哈希前缀)。同名不同码→冲突，阻断该成员或拆分报告。phase2 按 cell 报告（每 cell K 来自其冻结 manifest）；跨 cell 汇总仅用显式 pooling 规则并标注。**K_eff 不再使用**；改报 K_raw、K_unique、唯一结果向量数（分子分母同口径：均含或均不含 bare，两种都报）。
- oracle(x) = max over (h, r, c) in 指定单次执行矩阵；oracle 覆盖 = E_D oracle(x)。best-fixed（held-out 口径单列）= max_h E_D Y[h,x,r=指定,c]；dev-fixed = 仅用开发数据（MATH 前 100；BIRD dev split）选出的单成员。headroom = oracle − best-fixed。headroom ≠ 实际收益。
- 任务分布 D：MATH-500 eval 400 任务；BIRD 对应冻结 split。抽样层级 = 任务（MATH）/ (数据库, 任务)（BIRD）；不确定性以任务为独立单位 bootstrap，重叠切分/seed 不计独立证据。
- 单次 residual coverage = oracle − bare（同一矩阵）；不外推条件期望净增益。条件期望 q_h(z)=E[Y_h|Z=z] 仅在同条件重复可交换假设下讨论；跨时间/提供方漂移的批次标记 non_exchangeable，只入 C 类证据的降权层，不并入主估计。
- pre-execution 信息 Z：任务元数据、开发集成员准确率、代码指纹（哈希/结构特征）。候选输出/轨迹/答案属 post-execution 信息，禁止进入 D 类主口径。
- 成本口径：logical calls、缓存命中数、执行次数按存档字段报告；token/费用字段缺失→成本缺失状态，不从调用数推算账单。
- 判分器：v1 = 存档原判分器（已验证 14400/14400 重放一致）；v2 = 端点敏感 + 括号一致判分器。所有结论标注判分器版本；两版本差异逐条可查。

## 3. 五类命题（estimand + 判定规则，冻结）

每类输出状态 ∈ {SUPPORTED, REFUTED_WITHIN_SCOPE, INSUFFICIENT_EVIDENCE, NOT_APPLICABLE} + 依据 + 适用范围 + 最小缺失证据 + **允许的结论句式**。类间不合并为总分。

- **A 测量充分性**。estimand：manifest 一致性、判分器重放一致性、身份唯一性、重复条件完整性（二值检查集）。输入：manifest + 全部结果行。判定：全部检查通过→SUPPORTED；任一阻断（重复键、verdict 重放不一致、缺失成员超 1%）→REFUTED_WITHIN_SCOPE（修复后可重评）；检查不可运行→INSUFFICIENT_EVIDENCE。允许句式："成员/任务/判分器/执行条件足以支持 §3.B–E 的指定比较"或"在 X 方面不足"。
- **B 单次额外覆盖**。estimand：headroom = oracle − best-fixed（点估计 + 任务 bootstrap 95% CI）。输入：指定单次执行矩阵。判定：CI 下界 > 0→SUPPORTED（仅限"该矩阵存在未利用覆盖"句式）；上界 < 0→REFUTED_WITHIN_SCOPE；否则 INSUFFICIENT_EVIDENCE。**禁止**外推到稳定/可部署。
- **C 稳定条件优势**。estimand：对成员对 (h1,h2)，同条件重复数 R≥3 且覆盖 ≥30 任务时，条件正确率差 Δ 的配对区间（任务层 bootstrap；非交换批次降权单列）。判定：R<3 或任务 <30→INSUFFICIENT_EVIDENCE（显式弃权，非"无差异"）；Δ 区间不含 0 且符号跨重复一致→SUPPORTED（"在指定任务/条件下稳定"）；区间不含 0 但符号不一致→REFUTED_WITHIN_SCOPE。存档现状预期：MATH 无匹配重复→C 全类 INSUFFICIENT_EVIDENCE，这本身是合法结果。
- **D 执行前可选择性**。主 estimand：冻结选择策略 π_Z（输入仅 Z）的期望正确率 − **dev-fixed**（dev-fixed 是无逐任务信息时可达到的参照；best-fixed 需观察评估结果，只作描述性参照）。π_Z 冻结为：逻辑回归（特征=开发集成员准确率向量 + 任务元数据 one-hot），开发集内 5 折交叉验证训练，MATH eval/BIRD 测试 split 上评估；动作空间 = 选择单成员（可 abstain：当 top-2 打分差 < ε=0.05 时选 bare）。判定：π_Z − dev-fixed 配对差 CI 下界 > 0→SUPPORTED（"执行前信息可识别"）；上界 < 0→REFUTED_WITHIN_SCOPE；否则 INSUFFICIENT_EVIDENCE。辅助描述量：π_Z − best-fixed（仅报告，不作 SUPPORTED 依据）。任务级 holdout，禁止测试任务信息入训练。Z 不足导致的弃权记 INSUFFICIENT_EVIDENCE 并报告弃权率，不写"无效果"。
- **E 实际策略效用**。P 冻结为 = π_Z 单成员选择（每任务恰好 1 次 logical call）；比较对象 = dev-fixed（同样每任务 1 次调用），**按构造成本匹配**；oracle-routing（K 次调用/任务）因成本不可匹配，仅作 post-execution 上界参照，不入 E 判定。净效用 U = (P 准确率 − 比较对象准确率) − λ·(P 伤害率 − 比较对象伤害率)，伤害率 = 答错且 bare 答对的任务比例，**λ 冻结为 1**（伤害与收益同权重，1:1 计入）。预算 b：每任务 ≤1 次 logical call（P 与比较对象同预算）；存档若无法验证调用计数则 E 记 INSUFFICIENT_EVIDENCE（强制）。token/费用字段缺失→成本缺失状态，不从调用数推算账单，E 不得 SUPPORTED。判定：U 的配对任务 bootstrap CI 下界 > 0→SUPPORTED（限定"该策略、该预算、该任务分布"）；上界 < 0→REFUTED_WITHIN_SCOPE；否则 INSUFFICIENT_EVIDENCE。

## 4. 诊断流程（S1–S5，逐项可执行）

输入：显式 manifest（成员清单+哈希、任务清单、判分器版本哈希、执行条件、结果文件+行号）。禁止扫目录定集合；重复键报错不覆盖。

S1→A；S2 分解（oracle/best-fixed/dev-fixed/bare，同矩阵）→B；S3 同条件重复检查与稳定性→C；S4 信息条件与 π_Z→D；S5 成本口径→E。缺失传播规则（继承 revision README 既有约定）：unknown/失败记录保留在分母并标记，不重试填洞、不计为 wrong、不用部分池宣称完整；K=0/K=1 cell 单列；跨批次不拼接凑主要终点。

## 5. 方法验证（校准/盲测分离，冻结协议）

- 控制包 = 版本化 JSON（每控制：生成机制代码、参考答案契约、预期 A–E 状态、独立实例数），SHA256 绑定，**先冻结后运行**。**控制清单冻结为 8 类 × 2 独立实例 = 16 个**：C1 相同输出不同代码；C2 同代码随机单次 gap 无 pre-execution 优势；C3 单成员始终占优的跨任务差距；C4 真实稳定交叉优势+Z 可识别（D/E 正控制）；C5 交叉优势但 Z 不足（弃权正控制）；C6 计入成本后净优势消失；C7 headroom 主要由 best-fixed 下降驱动；C8 完整性类（缓存耦合/重复身份/缺失成员/损坏判分器/小样本）。calibration 集 = 每类实例 #1（8 个）；blinded 集 = 每类实例 #2（8 个）+ Astra 挑战 **恰 2 个**（挑战数冻结为 2；Astra 在任何结果可见前以哈希提交挑战契约与预期状态）→ **N_blinded = 10（固定）**。
- 通过条件（冻结，分母全部由冻结的预期状态清单派生，不再硬编码）：(i) 错误支持率 = blinded 集假 SUPPORTED 数 / **N_nonSUPPORTED**（= 冻结预期状态 ≠ SUPPORTED 的 blinded 控制数，含挑战，冻结时记入 manifest）≤ 0.1；(ii) 正控制识别：C4 的 blinded 实例与 Astra 挑战中的正控制在 D/E 必须 SUPPORTED；(iii) 弃权校准：C5 与 Astra 挑战中的弃权类必须 INSUFFICIENT_EVIDENCE；(iv) **弃权上限** = 3 / **N_clear**（N_clear = 冻结预期状态 ∈ {SUPPORTED, REFUTED_WITHIN_SCOPE} 的 blinded 控制数，含挑战）；(v) 错误定位：每个假状态须可追溯到 S1–S5 具体步骤。挑战控制进入全部指标，其预期状态由 Astra 哈希预提交。只支持易正控制而其余全弃权被 (ii)+(iv) 联合排除。
- 指标：错误支持率、识别率、弃权率、定位率、诊断计算开销（wall time）。样本单位=控制实例（机制级独立）。
- 方法比较（同一控制集+同一冻结阈值）：M0 仅传统 population 指标；M1 分解基线（oracle/best-fixed 正确分解 + glob 去重/NaN 完整性检查）；M1b = M1 + 固定 comparator 策略（dev 选择 + bare fallback）与成本匹配规则；M2 完整诊断；M3 消融（−重复检查 / −信息条件）。报告各方法 × 各控制的判定矩阵。M2 无增益则如实降级贡献声明。

## 6. 真实存档验证（回顾性，标注）

对象：MATH-500 存档、BIRD phase2 replay 范围、revision_20260910 repeat 记录。
- **全量清单强制**：`ARCHIVE_INVENTORY.csv` 覆盖存档全部记录/cell/成员行，每行状态 ∈ {included, excluded(理由), unknown, failed, abstained, unclosed, never_started}；代表案例按预冻结规则选取（影响幅度 top + 每类机制 1 例 + 随机 1 例），不替代全量表。
- MATH 判分器 v2 全量重评：逐条差异 + 汇总；final_answer 截断致无法重评的记录显式列出（不补造答案、不缩分母）。
- 决策变化记录（DECISION_IMPACT.csv 每行）：原可核对陈述→仅原指标判断→完整诊断判断+依据→改变类型（数值/排序/支持范围/下一动作）→可复现位置→历史行为证据有无（回顾性重建单独标）。预先声明：全部保持原判断也是合法结果，此时论文贡献改述为"测量限制与不可识别性证据"。
- 失败/unknown 传播按 §4；预期 E 类在真实存档 INSUFFICIENT_EVIDENCE，如实报告。

## 7. 已知解释陷阱（诊断输出强制核对清单）

单次 oracle gap≠稳定优势；gate 准入语义≠verification 效应；K_eff 口径（已废除，见 §2）；union 指标命名（`union_all_fail_rate`/`any_candidate_fail_rate` 显式分名）；clone headroom 不可相减去噪；打败 dev-fixed≠打败 best-fixed；logical calls≠账单。

## 8. 交付物

`experiment/diagnostics/{cli.py, core.py, math_adapter.py, bird_adapter.py, controls.py, test_*.py}`；`CONTROL_VALIDATION.json`（含控制包哈希、阈值版本、M0–M3 矩阵）；`ARCHIVE_INVENTORY.csv`；`DECISION_IMPACT.csv`；`CLAIM_EVIDENCE.json`（含 A–E→论文句子/图表映射 + 状态词白名单/外推词黑名单）；`REPRODUCE.md`。无模型 API 可复现；实测平台 Windows/Python 3.13，不声称跨平台。A–E 状态词映射：SUPPORTED/REFUTED_WITHIN_SCOPE/INSUFFICIENT_EVIDENCE/NOT_APPLICABLE 仅在本定义口径下使用；论文禁用"证明可部署""跨域普适""稳定互补（无 C 证据时）"。中英稿同步检查列入终审。

## 9. 完成标准映射（A–E 完成度）

A 缺陷修复版本化+影响报告；B 入口可执行（S1–S5 全通）；C 控制验证达 §5 通过条件；D 全量清单+决策影响可复现；E 稿件一致+独立终审。不足时交付现状+最小缺口。

## 10. 修订对照

v1.0→v1.1（审核意见 1–12）：1→§3（A–E estimand/判定/句式）；2→§2（Y[h,x,r,c] + 重复定义）；3→§3.C（R≥3、任务≥30、配对区间、非交换降权）；4→§2（K_raw/K_unique/身份键/cell 口径，废除 K_eff）；5→§3.D（π_Z 冻结、5 折 CV、holdout、abstain 规则）；6→§3.E（P、成本匹配、U、缺失强制弃权）；7→§5（两阶段、每类≥2 实例、Astra 盲挑战哈希预提交）；8→§5（哈希绑定控制包、阈值冻结可审计）；9→§5（M1b comparator+成本匹配）；10→§6/§8（ARCHIVE_INVENTORY.csv 全量、预冻结选例规则）；11→§4（unknown/失败传播继承既有约定）；12→§6（零改变合法、贡献绑定可复现证据）。
v1.1→v1.2（复核新增阻断 + 残留）：6 残留→§3.E（P 冻结为 π_Z 单成员选择、b=1 call/任务、λ=1、oracle-routing 降为参照）；新增 1→§3.D（D 主 estimand 与判定统一为 π_Z − dev-fixed，π_Z − best-fixed 降为描述性参照）；新增 2→§5（控制清单冻结为 8 类×2 实例=16，blinded=8+挑战，分母显式）。
v1.2→v1.3（第 3 轮复核唯一残留，按审核者规范修订）：挑战数冻结为恰 2，N_blinded=10 固定；分母 N_nonSUPPORTED/N_clear 改为由冻结预期状态清单派生并在冻结时记入 manifest；挑战控制进入全部指标。**本轮方法/验证合同自 v1.3 起冻结（FROZEN v1.0）**。
