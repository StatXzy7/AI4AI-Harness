# 诊断流程计划 v2.0（2026-09-15，响应外部复审的修订版）

状态：本文件是 `DIAGNOSTIC_PLAN_20260915.md`（v1.3 = FROZEN v1.0）的修订层。
v1.3 原文保持原样，作为历史冻结快照；本版仅记录对它的修订与新增，并说明
每项修订对应的外部复审（Codex 独立审稿，2026-09-15，评分 4/10）问题编号。
凡本版与 v1.3 冲突之处，以本版为准。

## 0. 修订来源

外部复审确认的实现问题（原文见复审意见"问题一/问题二/问题四"）：
1. S3 稳定性判定的群体结论依赖成员列表顺序（复现：同一群体仅交换成员排列，
   C 类从 REFUTED_WITHIN_SCOPE 反转为 SUPPORTED）。
2. S3 不核验所声称的执行条件：condition 字段与跨重复 source_hashes 均未比较，
   也没有重复独立性检查。
3. S3 的"稳定总体差"与论文标题的"任务–harness 交互"（互补性）是两个不同
   命题，代码把它们混为一个。
4. 控制验证的 blinded 阶段重放历史 `astra_challenges_result.json`（按目录
   排序选取、未绑定代码哈希），而非用当前代码重执行挑战。
5. A 类把"未执行 judge replay"传成 mismatches=0，"未执行"被渲染为"通过"。
6. E 类把"适配器未读取调用数"与"存档无调用记录"混同为同一状态（BIRD 行内
   实际有 n_llm_calls 字段）。
7. 冻结计划的验证单位/分母与实现口径不一致；挑战缺失时静默降级为只跑基础
   控制。

## 1. C 类拆分为两个 estimand（对应问题 1/3）

v1.3 §3.C 的单一 C 类拆为：

- **C-rank（稳定条件排序）**：对成员对 (h1,h2)，同条件重复下的条件正确率差
  的配对区间 + 跨重复符号一致性。**方向由成员 ID 的字典序固定，与输入排列
  无关**（排列不变性为结构性保证，见 §3）。群体级状态 SUPPORTED ⟺ 存在
  至少一个方向对具有稳定差（任一方向）。v1.3 的 R≥3、任务≥30、bootstrap
  规则不变。
- **C-comp（稳定互补性 / 任务–harness 交互）**：
  H_stable = E_x max_h q_h(x) − max_h E_x q_h(x)，q_h(x) 为重复平均的期望
  正确率。H_stable = 0 ⟺ 存在单一成员在所有任务上期望最优（全局占优）。
  两成员情形满足恒等式
  H_stable = E[Δ(x)_+] − (E[Δ(x)])_+ = (E|Δ(x)| − |E Δ(x)|)/2，
  其中 Δ(x) = p1(x) − p0(x)。**C-rank SUPPORTED 不允许写成互补性**；
  全局占优群体的 C-comp 必须为 REFUTED_WITHIN_SCOPE。
  已知偏差：q̂ 由 R 次重复估计，E[max] 对噪声上偏；输出强制携带该 caveat。

两者在报告中并列输出（`stable_ranking` / `stable_complementarity`），顶层的
`state` 字段 = C-rank 的群体状态（与 v1.3 的 C 类字段向后兼容）。

## 2. 重复执行身份门（对应问题 2/7）

以下三项任一命中，S3 拒绝合并并返回 INSUFFICIENT_EVIDENCE（显式弃权，
逐项列出违例）：
1. **条件字段一致性**：所有重复的 `condition` 逐字段完全相等；
2. **成员身份一致性**：同一成员在所有重复中的 `source_hashes` 完全相等
   （变更源码冒充重复 → 拒绝）；
3. **重复独立性**：任两个重复的结果矩阵完全逐元素相等 → 拒绝（克隆矩阵
   冒充独立执行 → 拒绝）。

## 3. 不变量测试义务（对应问题 1）

控制验证从"断言当前输出"升级为"科学结论必须满足的不变量"，至少包括：
- 排列不变性：仅交换成员列表顺序（id→数据映射不变），群体结论与成对报告
  逐项不变；
- 占优 ≠ 互补：全局占优群体 C-rank SUPPORTED 且 C-comp REFUTED；
- 交叉互补：总均值相等但跨任务优势交叉的群体，C-rank INSUFFICIENT 且
  C-comp SUPPORTED；
- 条件混合 / 克隆重复 / 身份变更三类输入必须被阻断。
以上已实现为 `TestS3Invariants`，全部离线、无模型调用。

## 4. 控制包 v2（对应问题 7 及"验证完整性"）

- v1 的 8 类 × 2 实例 = 16 个控制与其冻结预期**原样保留**（历史快照不覆盖）。
- 新增重复类控制 4 类 × 2 实例 = 8 个：C9 全局占优（rank SUPPORTED 且
  comp REFUTED）；C10 交叉互补（rank INSUFFICIENT 且 comp SUPPORTED，
  D/E SUPPORTED）；C11 条件混合陷阱；C12 克隆重复陷阱。
- 控制包总数 24；blinded = 12 + 2 挑战 = 14（固定）。
- 判定阈值沿用 v1.3 §5（错误支持率 ≤ 0.1；弃权上限 3 或 N_clear 的 30%），
  单位 = 控制×类 cell（实现口径，此处显式声明；v1.3 的"控制实例"口径同时
  以 per-control any-wrong 报告）。
- 冻结序：v2 预期状态在本次盲测运行前写入 `build_package()` 并随
  manifest_sha256 固化；新增类的预期由生成机制解析导出（文档化于
  controls.py docstring），非由被测程序导出。

## 5. 挑战执行链（对应问题 4）

- **当前实现验证**：blinded 阶段用当前代码从冻结 spec（SHA256 绑定
  `challenge_spec.sha256`）重执行 CH1/CH2，输出绑定
  {spec_sha256, 逐模块 code_sha256, 输入生成规则, 结果}。spec 缺失或哈希
  不符 → 硬阻断，不得静默跳过。
- **历史结果重放**：`verify-challenges --challenge-result P` 单独命令，仅
  核验指定历史文件的 spec 绑定并输出 HISTORICAL_REPLAY 状态；不进入当前
  验证指标。禁止目录排序自动选取"最新结果"。
- 复审发现的实证：历史 `astra_challenges_result.json` 的 CH2 数值
  （best_fixed=0.94）在 spec 生成规则下不可达（规范强制 0.79），其存储的
  CH2-D=REFUTED 系当时未绑定实现的执行器产物；规范忠实重执行结果为
  CH2-D=SUPPORTED、E=REFUTED，与 Astra 预期一致。历史文件保留作溯源。

## 6. A 类执行状态语义（对应问题 5）

- judge replay 证据必须携带状态 ∈ {executed, not_executed, infeasible}；
  仅 executed 且 mismatches=0 可为通过；未执行/不可执行 → 该检查记
  not_run，A 类至多 INSUFFICIENT_EVIDENCE，**不得 SUPPORTED**。
- 违例（mismatches>0 等）→ REFUTED_WITHIN_SCOPE（原语义不变）。

## 7. 成本与缺失语义（对应问题 6）

- calls 证据状态 ∈ {per_record, aggregate_only, absent_in_archive_rows,
  not_provided}；"未提供"必须显式说明不构成"存档无记录"的证据。
- BIRD 适配器现读取行内 `n_llm_calls`（core 子集 288,104 次逻辑调用），
  E 类弃权理由相应改为"无 dev/eval 切分可训练策略"，不再声称"无成本数据"。
- 成对比较新增缺失敏感界（所有未知格的最优/最劣填充下成对差的上下界），
  与保守的已记录成功率并列输出；`_acc` 命名为 recorded success rate，
  不声称是未知真值的假设自由估计。

## 8. MATH judge-v2 重评的历史声明更正（复审后新发现）

在哈希绑定的当前代码下重跑全部 14,400 条 MATH 判分的 v2 重评，得到
**14 处翻转（0 假接受，14 假拒绝），全部集中在任务 math500_split#103
（gold = "(3,4]"，区间端点题）**；v1 重放本身 0 失配（存档内部一致）。
历史产物（2026-09-15 06:19 生成，早于 10:26 提交）声称 0 翻转，且其
manifest 哈希与当前一致——即该声明不可能由已提交代码产生，属未绑定
实现的历史验证产物。论文相应句子由"changed none"更正为如实数字。
影响范围：单任务、全部为 v1 假拒绝（v2 更正确）；受影响成员单任务
准确率 +0.25pp（400 任务口径）；不改变任何定性结论。

## 9. 交付物增补

- `experiment/diagnostics/challenges.py`（规范忠实执行器 + 哈希绑定）；
- 控制包 v2 manifest、`control_validation_{phase}.json`（含
  challenge_execution 绑定块）；
- `TestS3Invariants` / `TestS1ExecutionState` / `TestChallengeExecution`
  不变量测试；
- `challenge_historical_replay.json`（历史重放报告）。

## 10. 第二轮复审修订（2026-09-15，响应 Codex recheck 6.5/10 的四项阻断）

- **E 类预算门（对应 recheck 阻断 1）**：冻结合同"存档若无法验证调用计数
  则 E 记 INSUFFICIENT_EVIDENCE（强制）"现在由代码强制执行：E 离开
  INSUFFICIENT 需要预算可核验——逐记录调用证据（calls_status=per_record）
  或设计例外 `budget_by_construction`（仅限合成控制：1-call 预算是生成
  机制的一部分，即 plan §3.E 的"按构造成本匹配"的显式化）。预算不可核验
  时即使 U 区间为正或为负也记 INSUFFICIENT，且输出不得被解读为"无效应"。
  该例外经本节修订记录在案，预期状态无需改动（C4/CH1 的 E SUPPORTED 从
  此有显式合同依据）。
- **D 策略实现与冻结合同一致（对应 recheck 阻断 2；含对第一版实现的
  更正）**：π_Z 按 plan §3.D 的"开发集内 5 折交叉验证"实现——按特征
  模式（strata）排序后全局轮转的分层 5 折，**每折模型在其余 4 折上训练**
  （fold_of != f）、对 eval 预测，eval 概率 = 折模型平均；特征 = 任务
  stratum one-hot + plan §3.D 要求的开发集成员准确率向量（常数列）；
  eval 行永不进入拟合。**更正记录**：第一版实现（commit 04532b3）把
  折方向写反（用 held-out 折训练）且缺 dev-acc 特征，被第二轮复审
  （5.5/10）指出，本版为修正后实现；修正经方向性参考实现测试
  （test_cv_direction_matches_reference_implementation）钉死。全部冻结
  预期状态经重跑确认不变（40/40 测试、24 控制、2 挑战全对）。
- **条件比较类型安全（对应 recheck 阻断 3）**：S3 的执行条件一致性检查
  改为 canonical typed JSON（`json.dumps(sort_keys=True)`），`60` 与
  `"60"` 是不同条件；新增回归测试。
- **C-comp 缺失传播（对应 recheck 阻断 4）**：任何 (member, task) 格在
  全部重复中无有效观测时，其期望不可识别；此时 C-comp 弃权
  （INSUFFICIENT，列出未识别格），不再对未知格做 0 填充——0 填充可能
  制造假占优或假互补。新增回归测试。
- **论文措辞**：E 类统一改称 budget-matched policy utility（不再用
  "deployable"），并在文中注明预算门语义。
- 复审原始意见存档：`review-stage/codex_recheck_20260915/recheck_last_message.txt`。

## 11. 第三轮复审修订（recheck2 5.5/10 -> recheck3 6.8/10 的三项修复 + 残项）

- **CV 折方向更正（recheck2 阻断 1）**：见 §10 更正记录；折模型在其余
  4 折上训练（fold_of != f），特征含 dev-accuracy 向量，方向由
  `test_cv_direction_matches_reference_implementation` 对照显式参考实现钉死。
- **E 预算验证严格化（recheck2 阻断 2 + recheck3 残项）**：逐记录证据必须
  覆盖全部 (member, task) 格且每值为有限非负数值 ≤ BUDGET_CALLS；
  aggregate_only、部分记录、超预算、NaN/inf/负值/非数值一律
  INSUFFICIENT，basis 字符串区分 malformed / calls_status /
  per_record_incomplete / over_budget；测试覆盖全部边界（含 NaN 显式用例）。
- **条件恒等整体 canonical 化（recheck2 阻断 3）**：比较整个 condition
  对象的 typed JSON，`{}` 与 `{"timeout": null}` 是不同条件；mismatch
  字段单列。
- **C-comp 缺失门（recheck1 阻断 4，本轮复审确认）**：保持不变。
- 目录名勘误：REPRODUCE.md 中 calibration/blinded 目录标注已修正
  （d3a32145=blinded，e721360b=calibration）。
- **E 门聚合健壮性（recheck4 残项）**：median_calls 只聚合有效值（有限
  非负数值），字符串/mixed/inf/负值/None/bool 等畸形记录不再使 s5 崩溃，
  一律走 malformed 门 -> INSUFFICIENT；测试覆盖全部畸形类型
  （test_malformed_call_values_never_crash）。
- recheck2/3/4 意见存档：`review-stage/codex_recheck_20260915/
  recheck{2,3,4}_last_message.txt`。
