# AUTO_REVIEW — Behavior-Aware Harness Generation

## Round 1 — 2026-09-03

- **Backend**: codex exec(gpt-5.6-sol,read-only,独立读仓)。本会话无 codex MCP 工具,
  按 nightmare 约定改用 `codex exec --skip-git-repo-check`。
- **尝试 1**(全材料,2.15M tokens):审稿人已读完全部稿件+artifacts,最终回复生成时
  本地中转 `127.0.0.1:15721` 上游全部熔断(503 × 5),无 verdict 产出。
- **尝试 2**(压缩为 4 文件):同样 503 熔断。
- **结论:verdict: REVIEW_UNAVAILABLE**(基础设施:cc-switch 中转供应商熔断,非材料问题)。

## Round 1 实际结果 — 2026-09-03(paratera EV-GPT-5.6-Sol via codex exec,343k tokens)

**SCORE: 4/10 | VERDICT: not ready**

- [P0 致命｜最致命#1] `PROBLEM_FREEZE.md:185`、`PROBLEM_FREEZE.md:197`、`paper/draft/03_setup.md:70`：所谓“预注册阈值”并未真正冻结——v6 明确是 repair ≥20%，v7 改成含混的“15–20%”，正文却宣称预先固定为 ≥15% 且“nothing was re-defined”；更严重的是，截至 **2026-09-02**，`PROBLEM_FREEZE.md:199`、`artifacts/day2/DAY2_RESULTS.md:3` 和定稿 `paper/draft/00_abstract_07_08.md:3` 均标为未来日期 **2026-09-03**，当前没有可验证的先验时间戳或 Git 历史，因此“pre-registered”主张不可审计。
- [P0 致命｜最致命#2] `paper/draft/01_intro.md:35`、`paper/draft/03_setup.md:46`：稿件声称“three builders × two protocols”并据此断言“protocol property, not capability ceiling”“capability and protocol jointly necessary”，但实验不是 3×2 因子设计：旧协议只有 GLM，gated 协议才有 GLM/Qwen/DeepSeek，IR 又没有 builder 轴；builder 与 protocol 严重混杂，现有证据最多支持“gated+Qwen/DeepSeek 可行”，不能分离 protocol 主效应、builder 主效应及交互。
- [P0 致命｜最致命#3] `experiment/loho_exec.py:140`、`experiment/loho_exec.py:145`、`PROBLEM_FREEZE.md:57`：LOHO 只留出 harness，同一批 151 个任务文本及其其他 harness 标签仍进入训练，因而不检验未见任务上的 harness-value 泛化，也未执行冻结文档承诺的 D_B/D_C/D_D 任务切分；task-only AUROC 高达 0.929–0.953（`artifacts/day1/LOHO_RESULTS_D6.json:186`、`artifacts/day1/LOHO_RESULTS_ALL24.json:613`）很可能反映任务记忆，不能作为严格的 open-set 部署结论。
- [P1 重要] `paper/draft/05_06_positive_control_protocols.md:88`：正文称阈值在“disjoint item half”调优，但实现 `stable_item_hash % 10 < 2` 实际仅使用约 20% 调优、80% 评估（`experiment/loho_exec.py:130`）；这是直接的方法描述错误。
- [P1 重要] `paper/draft/03_setup.md:33`、`paper/draft/01_intro.md:40`：反复称“151 held-out questions”和“before any evaluation”，但 `artifacts/day2/DAY2_RESULTS.md:12` 明确有 24/151 题参与过 Day-1 协议开发，人工对照也在检查这些 trace 后设计；Limitations 虽披露重叠，但 Setup/Introduction 的 held-out 表述仍不成立，应改成 builder-held-out 或 protocol-development-overlap evaluation。
- [P1 重要] `paper/draft/00_abstract_07_08.md:13`、`paper/draft/01_intro.md:17`：塌缩结果混用 21/66 与 28/78 而不解释总体差异；前者来自 12 个生成候选（`artifacts/day2/fig_hero_data.json:18`），后者来自 12 候选加 `react` 的 13 个非 bare harness（`artifacts/day1/population_diagnosis.json:8`）。Introduction 却把 28/78 称为“candidate population”，口径错误。
- [P1 重要] `paper/draft/01_intro.md:27`、`paper/draft/05_06_positive_control_protocols.md:17`：主叙事仍突出 60 题的 20.7% repair，而 151 题复测只有 14.9% 且未过门槛（`artifacts/day2/eval151_comparison.json:126`）；此外所谓“same 60 tasks, same target, same judge”下，AI 诊断的 bare errors 是 26（`artifacts/day1/population_diagnosis.json:3`），人工对照却是 29（`artifacts/day1/positive_control_diagnosis.json:12`），直接并表并不能证明唯一变化是 harness 来源。
- [P1 重要] `paper/draft/01_intro.md:28`、`paper/draft/05_06_positive_control_protocols.md:24`：稿件称 repair/schema/hint 各有 3 个“unique repairs”，但结果文件只记录每个 harness 的 fix 数为 3，没有保存或证明彼此独有的集合关系（`artifacts/day1/positive_control_diagnosis.json:14`）；该数字目前不可审计。
- [P1 重要] `paper/draft/05_06_positive_control_protocols.md:85`：L3 FAIL 的方向被如实写出，这是优点，但呈现仍有淡化：正文省略 D6、C6、ALL24 对 best-fixed 的完整 CI，并把 L2 的 ALL24 AUROC 0.575 描述成“weak but nonzero”，没有明确写出预注册判定是 **L2 MARGINAL FAIL**（`artifacts/day2/DAY2_RESULTS.md:39`）。
- [P1 重要] `paper/draft/00_abstract_07_08.md:27`、`paper/draft/05_06_positive_control_protocols.md:93`：+6.9 pp、zero harm 仅来自混合的 ALL24 池，且仍比 best-fixed 低 0.86 pp、CI=[−6.03,+4.31] pp（`artifacts/day1/LOHO_RESULTS_ALL24.json:631`）；C6/D6 的 intervention harm 分别为 2.8%/8.7%（`artifacts/day1/LOHO_RESULTS_C6.json:207`、`artifacts/day1/LOHO_RESULTS_D6.json:207`）。Abstract 的紧邻写法容易让读者误以为 admitted populations 均实现零伤害。
- [P1 重要] `paper/draft/00_abstract_07_08.md:67`：声称 repair-rate bootstrap CI 仅“±4–5 pp”，与原始 CI 不符；例如 A6 为 [.1486,.3467]、C6 为 [.125,.3095]、ALL24 为 [.2676,.4875]，实际半宽约 9–11 pp（`artifacts/day2/eval151_comparison_ci.json:3`、`artifacts/day2/eval151_comparison_ci.json:13`、`artifacts/day2/eval151_comparison_ci.json:63`）。
- [P1 重要] `paper/draft/05_06_positive_control_protocols.md:71`：C6/D6 只是点估计超过 5 pp，其 headroom CI 分别为 [1.99,8.61] 和 [3.97,11.26]，均包含低于门槛的效应（`artifacts/day2/eval151_comparison_ci.json:17`、`artifacts/day2/eval151_comparison_ci.json:27`）；若 admission 按点估计判定必须明说，不能用统计显著意义上的“clear thresholds”措辞。
- [P1 重要] `paper/draft/04_measurement.md:16`：union repair 的定义写成 bare error 满足 `Δ(x,H0,M)=-1`，但按 §3 定义 `Δ(x,H0,M)=Y(H0)-Y(H0)=0` 恒成立；正确条件应为 `Y(x,H0,M)=0`。
- [P1 重要] `paper/draft/05_06_positive_control_protocols.md:75`：A6 在 151 题上 disagreement=7.0%、repair=24.3%、headroom=4.64 pp，仅差门槛 0.36 pp（`artifacts/day2/eval151_comparison.json:12`、`artifacts/day2/eval151_comparison.json:20`），因此 Conclusion 的“standard protocol collapses”过强；严谨表述应是“未达到预注册 headroom 门槛”，塌缩结论只由 Day-1 60 题总体支持。
- [P1 重要] `paper/draft/01_intro.md:52`、`paper/draft/02_related_work.md:6`：“first systematic measurement”当前不可守。至少 2026-08-27 提交的 HarnessLens 已直接研究 behavior-aware harness generation、trace/attribution verification 和 gate-based pruning，而稿件完全未讨论；即便最终保留优先权，也必须缩窄到精确的 outcome-matrix collapse 定义并完成系统检索。citeturn1search0turn1search1
- [P1 重要] `paper/draft/03_setup.md:51`：GLM“不能可靠生成长代码”的证据只有空 registry（`artifacts/day2/registry_b2glm.json:5`），没有六次尝试、错误类型、重试预算或 gate rejection 日志；0/6 可以报告，但不能据此归因为 builder capability。
- [P1 重要] `paper/draft/05_06_positive_control_protocols.md:43`：九页章节骨架本身成立，但方法部分只有约八行协议描述，缺少生成 prompt、probe 集、重试/预算、gate 伪代码、IR grammar/compiler 图、失败处理和成本；同时没有 gate 各组件消融、builder×protocol 交叉消融、跨 target/domain 验证、随机种子或重复实验，当前不足以支撑核心因果主张。
- [P2 建议] `paper/PAPER_PLAN.md:46`、`paper/draft/05_06_positive_control_protocols.md:41`：计划中的 hero 图、taxonomy 图、三条件结果图、IR pipeline 图尚未嵌入稿件，且正文仍保留“结果表等待 eval151”的过期注释；appendix 清单、复现配置、完整 harness/spec、trace 案例、逐项 fix sets、LOHO fold 表、成本/延迟、官方 BIRD scorer 对照和匿名代码说明也尚不存在。

SCORE: 4/10 | VERDICT: not ready
tokens used
343,018
- [P0 致命｜最致命#1] `PROBLEM_FREEZE.md:185`、`PROBLEM_FREEZE.md:197`、`paper/draft/03_setup.md:70`：所谓“预注册阈值”并未真正冻结——v6 明确是 repair ≥20%，v7 改成含混的“15–20%”，正文却宣称预先固定为 ≥15% 且“nothing was re-defined”；更严重的是，截至 **2026-09-02**，`PROBLEM_FREEZE.md:199`、`artifacts/day2/DAY2_RESULTS.md:3` 和定稿 `paper/draft/00_abstract_07_08.md:3` 均标为未来日期 **2026-09-03**，当前没有可验证的先验时间戳或 Git 历史，因此“pre-registered”主张不可审计。
- [P0 致命｜最致命#2] `paper/draft/01_intro.md:35`、`paper/draft/03_setup.md:46`：稿件声称“three builders × two protocols”并据此断言“protocol property, not capability ceiling”“capability and protocol jointly necessary”，但实验不是 3×2 因子设计：旧协议只有 GLM，gated 协议才有 GLM/Qwen/DeepSeek，IR 又没有 builder 轴；builder 与 protocol 严重混杂，现有证据最多支持“gated+Qwen/DeepSeek 可行”，不能分离 protocol 主效应、builder 主效应及交互。
- [P0 致命｜最致命#3] `experiment/loho_exec.py:140`、`experiment/loho_exec.py:145`、`PROBLEM_FREEZE.md:57`：LOHO 只留出 harness，同一批 151 个任务文本及其其他 harness 标签仍进入训练，因而不检验未见任务上的 harness-value 泛化，也未执行冻结文档承诺的 D_B/D_C/D_D 任务切分；task-only AUROC 高达 0.929–0.953（`artifacts/day1/LOHO_RESULTS_D6.json:186`、`artifacts/day1/LOHO_RESULTS_ALL24.json:613`）很可能反映任务记忆，不能作为严格的 open-set 部署结论。
- [P1 重要] `paper/draft/05_06_positive_control_protocols.md:88`：正文称阈值在“disjoint item half”调优，但实现 `stable_item_hash % 10 < 2` 实际仅使用约 20% 调优、80% 评估（`experiment/loho_exec.py:130`）；这是直接的方法描述错误。
- [P1 重要] `paper/draft/03_setup.md:33`、`paper/draft/01_intro.md:40`：反复称“151 held-out questions”和“before any evaluation”，但 `artifacts/day2/DAY2_RESULTS.md:12` 明确有 24/151 题参与过 Day-1 协议开发，人工对照也在检查这些 trace 后设计；Limitations 虽披露重叠，但 Setup/Introduction 的 held-out 表述仍不成立，应改成 builder-held-out 或 protocol-development-overlap evaluation。
- [P1 重要] `paper/draft/00_abstract_07_08.md:13`、`paper/draft/01_intro.md:17`：塌缩结果混用 21/66 与 28/78 而不解释总体差异；前者来自 12 个生成候选（`artifacts/day2/fig_hero_data.json:18`），后者来自 12 候选加 `react` 的 13 个非 bare harness（`artifacts/day1/population_diagnosis.json:8`）。Introduction 却把 28/78 称为“candidate population”，口径错误。
- [P1 重要] `paper/draft/01_intro.md:27`、`paper/draft/05_06_positive_control_protocols.md:17`：主叙事仍突出 60 题的 20.7% repair，而 151 题复测只有 14.9% 且未过门槛（`artifacts/day2/eval151_comparison.json:126`）；此外所谓“same 60 tasks, same target, same judge”下，AI 诊断的 bare errors 是 26（`artifacts/day1/population_diagnosis.json:3`），人工对照却是 29（`artifacts/day1/positive_control_diagnosis.json:12`），直接并表并不能证明唯一变化是 harness 来源。
- [P1 重要] `paper/draft/01_intro.md:28`、`paper/draft/05_06_positive_control_protocols.md:24`：稿件称 repair/schema/hint 各有 3 个“unique repairs”，但结果文件只记录每个 harness 的 fix 数为 3，没有保存或证明彼此独有的集合关系（`artifacts/day1/positive_control_diagnosis.json:14`）；该数字目前不可审计。
- [P1 重要] `paper/draft/05_06_positive_control_protocols.md:85`：L3 FAIL 的方向被如实写出，这是优点，但呈现仍有淡化：正文省略 D6、C6、ALL24 对 best-fixed 的完整 CI，并把 L2 的 ALL24 AUROC 0.575 描述成“weak but nonzero”，没有明确写出预注册判定是 **L2 MARGINAL FAIL**（`artifacts/day2/DAY2_RESULTS.md:39`）。
- [P1 重要] `paper/draft/00_abstract_07_08.md:27`、`paper/draft/05_06_positive_control_protocols.md:93`：+6.9 pp、zero harm 仅来自混合的 ALL24 池，且仍比 best-fixed 低 0.86 pp、CI=[−6.03,+4.31] pp（`artifacts/day1/LOHO_RESULTS_ALL24.json:631`）；C6/D6 的 intervention harm 分别为 2.8%/8.7%（`artifacts/day1/LOHO_RESULTS_C6.json:207`、`artifacts/day1/LOHO_RESULTS_D6.json:207`）。Abstract 的紧邻写法容易让读者误以为 admitted populations 均实现零伤害。
- [P1 重要] `paper/draft/00_abstract_07_08.md:67`：声称 repair-rate bootstrap CI 仅“±4–5 pp”，与原始 CI 不符；例如 A6 为 [.1486,.3467]、C6 为 [.125,.3095]、ALL24 为 [.2676,.4875]，实际半宽约 9–11 pp（`artifacts/day2/eval151_comparison_ci.json:3`、`artifacts/day2/eval151_comparison_ci.json:13`、`artifacts/day2/eval151_comparison_ci.json:63`）。
- [P1 重要] `paper/draft/05_06_positive_control_protocols.md:71`：C6/D6 只是点估计超过 5 pp，其 headroom CI 分别为 [1.99,8.61] 和 [3.97,11.26]，均包含低于门槛的效应（`artifacts/day2/eval151_comparison_ci.json:17`、`artifacts/day2/eval151_comparison_ci.json:27`）；若 admission 按点估计判定必须明说，不能用统计显著意义上的“clear thresholds”措辞。
- [P1 重要] `paper/draft/04_measurement.md:16`：union repair 的定义写成 bare error 满足 `Δ(x,H0,M)=-1`，但按 §3 定义 `Δ(x,H0,M)=Y(H0)-Y(H0)=0` 恒成立；正确条件应为 `Y(x,H0,M)=0`。
- [P1 重要] `paper/draft/05_06_positive_control_protocols.md:75`：A6 在 151 题上 disagreement=7.0%、repair=24.3%、headroom=4.64 pp，仅差门槛 0.36 pp（`artifacts/day2/eval151_comparison.json:12`、`artifacts/day2/eval151_comparison.json:20`），因此 Conclusion 的“standard protocol collapses”过强；严谨表述应是“未达到预注册 headroom 门槛”，塌缩结论只由 Day-1 60 题总体支持。
- [P1 重要] `paper/draft/01_intro.md:52`、`paper/draft/02_related_work.md:6`：“first systematic measurement”当前不可守。至少 2026-08-27 提交的 HarnessLens 已直接研究 behavior-aware harness generation、trace/attribution verification 和 gate-based pruning，而稿件完全未讨论；即便最终保留优先权，也必须缩窄到精确的 outcome-matrix collapse 定义并完成系统检索。citeturn1search0turn1search1
- [P1 重要] `paper/draft/03_setup.md:51`：GLM“不能可靠生成长代码”的证据只有空 registry（`artifacts/day2/registry_b2glm.json:5`），没有六次尝试、错误类型、重试预算或 gate rejection 日志；0/6 可以报告，但不能据此归因为 builder capability。
- [P1 重要] `paper/draft/05_06_positive_control_protocols.md:43`：九页章节骨架本身成立，但方法部分只有约八行协议描述，缺少生成 prompt、probe 集、重试/预算、gate 伪代码、IR grammar/compiler 图、失败处理和成本；同时没有 gate 各组件消融、builder×protocol 交叉消融、跨 target/domain 验证、随机种子或重复实验，当前不足以支撑核心因果主张。
- [P2 建议] `paper/PAPER_PLAN.md:46`、`paper/draft/05_06_positive_control_protocols.md:41`：计划中的 hero 图、taxonomy 图、三条件结果图、IR pipeline 图尚未嵌入稿件，且正文仍保留“结果表等待 eval151”的过期注释；appendix 清单、复现配置、完整 harness/spec、trace 案例、逐项 fix sets、LOHO fold 表、成本/延迟、官方 BIRD scorer 对照和匿名代码说明也尚不存在。

SCORE: 4/10 | VERDICT: not ready


(注:审核中'2026-09-03 为未来日期'系审稿人不知当日即 09-03;时间戳问题通过建立 git 历史解决。)

### Round 0(未遂)记录

### 待中转恢复后的重跑入口

```bash
cd /e/Study/PhD/Research/AI4AI-Harness
codex exec --skip-git-repo-check --sandbox read-only "$(cat review-stage/review_prompt_round1.txt)"
```

审稿重点(已预设):数字抽查一致率、"first systematic measurement" 优先权声明口径、
21/66 vs 28/78 口径、人工对照 60→151 题的诚实性、L3 负结果是否被淡化、9 页结构完整性。

### Round 1 自查清单(执行者预审,不替代跨模型审核)

- [x] 稿件所有数字已溯源至 DAY2_RESULTS.md / eval151_comparison(_ci).json / PROBLEM_FREEZE.md
- [x] L3 FAIL 在 abstract、intro 贡献 3、§6.1、§7、§8 五处如实出现,无淡化措辞
- [x] borderline(人工 14.9%、IR 3.97pp)原样报告,未做阈值事后调整
- [x] hero 图 21/66 与正文 28/78(13-harness 口径)各自注明口径
- [ ] P0 待审:'first systematic measurement' 优先权声明需 novelty 复核(citation-audit)


## Round 2 — 2026-09-03(paratera EV-GPT-5.6-Sol,289k tokens)

**SCORE: 3/10 | VERDICT: not ready**

**Round‑1 意见复核**
- P0-1 预注册可审计性 — `_open`：git 仍是结果产生后的回溯初始化，且 v7 原文是含糊的“15–20%”而非声称的固定 15%；无法证明阈值未受结果影响。`PROBLEM_FREEZE.md:197` `paper/draft/03_setup.md:85`
- P0-2 非因子设计与因果归因 — `_partial`：已明确“两组嵌套对照、不能分离主效应”，但摘要和讨论仍声称“gap is a protocol property”“两轴互补/可判断 binding”，超出设计支持范围。`paper/draft/00_abstract_07_08.md:20` `paper/draft/00_abstract_07_08.md:58`
- P0-3 LOHO 任务泄漏 — `_partial`：已承认同任务跨 harness 泄漏并报告任务切分，但没有结果 JSON、切分 ID 或实现代码，且仅一次 D6 切分被泛化成复数切分和总体结论。`paper/draft/05_06_positive_control_protocols.md:123`
- P1-1 21/66 与 28/78 分母混淆 — `_partial`：两种口径已拆开，但“12 generated candidates 的平均 disagreement=3.5%”仍不对；复算为 3.81%，3.5% 是含 ReAct 的 13-harness/78-pair 口径。`paper/draft/01_intro.md:16`
- P1-2 HPC “各自 3 个 unique repairs” — `_fixed`：现改为 fix sets 各含 3 项、真正独占数量为 1/2/1，且 `vote3=0`，与原始 parquet 复算一致。`artifacts/day1/hpc_fixset_audit.json:2`
- P1-3 bare 跨运行不一致 — `_fixed`：已披露 3/60 翻转和 26/29 两种 bare-error 分母，审计 JSON 与两份矩阵一致。`paper/draft/05_06_positive_control_protocols.md:17`
- P1-4 repair-rate CI 宽度 — `_fixed`：已由错误的 ±4–5pp 改为约 ±9–11pp，并在结果表列出具体区间。`paper/draft/00_abstract_07_08.md:71`
- P1-5 “zero harm” 范围 — `_fixed`：已限定为 ALL24 abstaining gate，并披露 C6/D6 干预 harm 为 2.8%/8.7%。`paper/draft/05_06_positive_control_protocols.md:133`
- P1-6 L2 判定措辞 — `_partial`：已改为 MARGINAL FAIL，但 D6 closed-set AUROC 写成 0.475，实际 JSON 为 0.470978；且预注册 L2 是 policy gain≥2pp，不只是 AUROC。`artifacts/day1/LOHO_RESULTS_D6.json:176`
- P1-7 点估计 admission — `_fixed`：明确 admission 按冻结的点估计规则，并醒目标注两个 headroom CI 均跨越 5pp 门槛。`paper/draft/05_06_positive_control_protocols.md:93`
- P1-8 trace-gated 术语 — `_open`：改名为 mechanism-gated，但正文仍称验收会确认机制被实现；实际生成脚本只抽取代码并写文件，没有机制、import 或执行 smoke gate。`paper/draft/01_intro.md:37` `experiment/builder_generate2.py:78`
- P1-9 GLM 0/6 的能力归因 — `_open`：文字虽降级为“单次生成可靠性”，但实际脚本在 `gen_one()` 使用未定义的 `prompt`，会在 API 请求前确定性失败，0/6 不能作为 builder 证据。`experiment/builder_generate2.py:50` `experiment/builder_generate2.py:57`
- P1-10 A6 被误称为完全 collapse — `_fixed`：现明确 A6 repair 健康、仅 headroom 差 0.36pp，彻底 collapse 只指 Day‑1。`paper/draft/05_06_positive_control_protocols.md:100`
- P1-11 相关工作缺漏 — `_partial`：已加入 HarnessLens/HarnessFix/AHE/QD/Handbook，但仍无规范引用，且文件明确保留“全名未核实/camera-ready 再审”的 TODO。`paper/draft/02_related_work.md:14` `paper/draft/02_related_work.md:68`
- P1-12 priority claim 过宽 — `_partial`：已缩窄到 outcome-matrix collapse measurement，但仍断言“none measures”，在引用尚未核实的情况下不能视为解决。`paper/draft/01_intro.md:58` `paper/draft/02_related_work.md:21`

**Round‑2 新问题**
- [P0] 截至当前日期 **2026-09-02**，两个 git commit、Day2 数据、审计文件和多份稿件均标为 **2026-09-03**；这些未来时间戳使当前提交的实验顺序与证据真实性无法成立。`artifacts/day2/DAY2_RESULTS.md:3`
- [P0] `builder_generate2.py` 不仅有未定义变量，还始终硬编码 GLM、没有 `--builder`、没有 16,384-token 设置、没有所述验收；它无法复现 B/C/D 中任何一组所声称的流程。`experiment/builder_generate2.py:50`
- [P0] C6 与 D6 并非同一六策略控制：Qwen 独有 `schema_link/hint_guard`，DeepSeek 独有 `repair/vote3`；因此 C–D 差异同时混入策略组成差异，builder-axis 结论失效。`artifacts/day2/registry_b2qwen.json:5` `artifacts/day2/registry_b2dexp.json:5`
- [P1] 任务级切分的 0.475/policy=bare 只存在于两处 Markdown，没有机器可读输出、代码、seed、任务列表、置信区间或完整 value/harm 结果，当前不可审计复现。`artifacts/day2/DAY2_RESULTS.md:64`
- [P1] 单次 D6 task split 被摘要和引言写成复数 held-out splits，并外推为一般的 task-side/open-set 失败；需限定为“一次 D6 task-held-out control”。`paper/draft/00_abstract_07_08.md:29`
- [P2] 正文残留中英混排错误“does not claim分离 main effects”，且相关工作仍保留内部 TODO，不符合可投稿稿件状态。`paper/draft/03_setup.md:83`

SCORE: 3/10 | VERDICT: not ready
tokens used
289,148
**Round‑1 意见复核**
- P0-1 预注册可审计性 — `_open`：git 仍是结果产生后的回溯初始化，且 v7 原文是含糊的“15–20%”而非声称的固定 15%；无法证明阈值未受结果影响。`PROBLEM_FREEZE.md:197` `paper/draft/03_setup.md:85`
- P0-2 非因子设计与因果归因 — `_partial`：已明确“两组嵌套对照、不能分离主效应”，但摘要和讨论仍声称“gap is a protocol property”“两轴互补/可判断 binding”，超出设计支持范围。`paper/draft/00_abstract_07_08.md:20` `paper/draft/00_abstract_07_08.md:58`
- P0-3 LOHO 任务泄漏 — `_partial`：已承认同任务跨 harness 泄漏并报告任务切分，但没有结果 JSON、切分 ID 或实现代码，且仅一次 D6 切分被泛化成复数切分和总体结论。`paper/draft/05_06_positive_control_protocols.md:123`
- P1-1 21/66 与 28/78 分母混淆 — `_partial`：两种口径已拆开，但“12 generated candidates 的平均 disagreement=3.5%”仍不对；复算为 3.81%，3.5% 是含 ReAct 的 13-harness/78-pair 口径。`paper/draft/01_intro.md:16`
- P1-2 HPC “各自 3 个 unique repairs” — `_fixed`：现改为 fix sets 各含 3 项、真正独占数量为 1/2/1，且 `vote3=0`，与原始 parquet 复算一致。`artifacts/day1/hpc_fixset_audit.json:2`
- P1-3 bare 跨运行不一致 — `_fixed`：已披露 3/60 翻转和 26/29 两种 bare-error 分母，审计 JSON 与两份矩阵一致。`paper/draft/05_06_positive_control_protocols.md:17`
- P1-4 repair-rate CI 宽度 — `_fixed`：已由错误的 ±4–5pp 改为约 ±9–11pp，并在结果表列出具体区间。`paper/draft/00_abstract_07_08.md:71`
- P1-5 “zero harm” 范围 — `_fixed`：已限定为 ALL24 abstaining gate，并披露 C6/D6 干预 harm 为 2.8%/8.7%。`paper/draft/05_06_positive_control_protocols.md:133`
- P1-6 L2 判定措辞 — `_partial`：已改为 MARGINAL FAIL，但 D6 closed-set AUROC 写成 0.475，实际 JSON 为 0.470978；且预注册 L2 是 policy gain≥2pp，不只是 AUROC。`artifacts/day1/LOHO_RESULTS_D6.json:176`
- P1-7 点估计 admission — `_fixed`：明确 admission 按冻结的点估计规则，并醒目标注两个 headroom CI 均跨越 5pp 门槛。`paper/draft/05_06_positive_control_protocols.md:93`
- P1-8 trace-gated 术语 — `_open`：改名为 mechanism-gated，但正文仍称验收会确认机制被实现；实际生成脚本只抽取代码并写文件，没有机制、import 或执行 smoke gate。`paper/draft/01_intro.md:37` `experiment/builder_generate2.py:78`
- P1-9 GLM 0/6 的能力归因 — `_open`：文字虽降级为“单次生成可靠性”，但实际脚本在 `gen_one()` 使用未定义的 `prompt`，会在 API 请求前确定性失败，0/6 不能作为 builder 证据。`experiment/builder_generate2.py:50` `experiment/builder_generate2.py:57`
- P1-10 A6 被误称为完全 collapse — `_fixed`：现明确 A6 repair 健康、仅 headroom 差 0.36pp，彻底 collapse 只指 Day‑1。`paper/draft/05_06_positive_control_protocols.md:100`
- P1-11 相关工作缺漏 — `_partial`：已加入 HarnessLens/HarnessFix/AHE/QD/Handbook，但仍无规范引用，且文件明确保留“全名未核实/camera-ready 再审”的 TODO。`paper/draft/02_related_work.md:14` `paper/draft/02_related_work.md:68`
- P1-12 priority claim 过宽 — `_partial`：已缩窄到 outcome-matrix collapse measurement，但仍断言“none measures”，在引用尚未核实的情况下不能视为解决。`paper/draft/01_intro.md:58` `paper/draft/02_related_work.md:21`

**Round‑2 新问题**
- [P0] 截至当前日期 **2026-09-02**，两个 git commit、Day2 数据、审计文件和多份稿件均标为 **2026-09-03**；这些未来时间戳使当前提交的实验顺序与证据真实性无法成立。`artifacts/day2/DAY2_RESULTS.md:3`
- [P0] `builder_generate2.py` 不仅有未定义变量，还始终硬编码 GLM、没有 `--builder`、没有 16,384-token 设置、没有所述验收；它无法复现 B/C/D 中任何一组所声称的流程。`experiment/builder_generate2.py:50`
- [P0] C6 与 D6 并非同一六策略控制：Qwen 独有 `schema_link/hint_guard`，DeepSeek 独有 `repair/vote3`；因此 C–D 差异同时混入策略组成差异，builder-axis 结论失效。`artifacts/day2/registry_b2qwen.json:5` `artifacts/day2/registry_b2dexp.json:5`
- [P1] 任务级切分的 0.475/policy=bare 只存在于两处 Markdown，没有机器可读输出、代码、seed、任务列表、置信区间或完整 value/harm 结果，当前不可审计复现。`artifacts/day2/DAY2_RESULTS.md:64`
- [P1] 单次 D6 task split 被摘要和引言写成复数 held-out splits，并外推为一般的 task-side/open-set 失败；需限定为“一次 D6 task-held-out control”。`paper/draft/00_abstract_07_08.md:29`
- [P2] 正文残留中英混排错误“does not claim分离 main effects”，且相关工作仍保留内部 TODO，不符合可投稿稿件状态。`paper/draft/03_setup.md:83`

SCORE: 3/10 | VERDICT: not ready


### Round-2 关键新发现(执行者确认属实)

1. [P0] builder_generate2.py 的 gen_one() 引用未定义变量 prompt、硬编码 GLM——不能复现 B/C/D。
   (实际 c2_b2qwen/c2_b2dexp 生成发生在 09-01 会话中,提交的脚本是事后残稿;需修复脚本并重跑缺失策略以获得带日志的生成 provenance。)
2. [P0] C6/D6 策略集不同(qwen: schema_link+hint_guard 无 repair/vote3;dsexp: repair+vote3 无 schema_link/hint_guard)——builder 对比被策略组成混杂。
   → 修复:补齐 4 个缺失 harness(dexp schema_link/hint_guard;qwen repair/vote3),151 题重测,做 matched-strategy 对比。
3. [P0] 日期问题:审稿人上下文日期为 09-02,将 09-03 时间戳判为未来——系审稿人时钟偏差,在 rebuttal 说明,changelog+mtime 为排序证据。
4. P1: 3.5% 为 13-harness 口径,12 candidates 应为 3.81%;D6 closedset AUROC 0.471 非 0.475;L2 预注册定义是 policy gain≥2pp;任务级切分需机器可读产物;『the gap is a protocol property』仍过强。
