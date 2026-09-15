# 七条待验证线索核验（2026-09-15，ZCode 主执行）

结论分级：CONFIRMED（缺陷/不一致属实，有可复现实例）/ CONFIRMED_MECHANISM_NO_IMPACT（机制属实、对冻结存档 verdict 零影响）/ NOT_CONFIRMED（未发现所述问题）。所有数值可由 `python -m experiment.diagnostics.cli`（本轮新增）或文中脚本复现。

## 1. MATH 区间规范化合并开闭端点 — CONFIRMED_MECHANISM_NO_IMPACT
- 代码：`experiment/gsm8k/collect.py:117-119`（`_norm_latex` 的不等式→区间正则把 `3<x<4` 与 `3<x<=4` 都写成 `(3,4]`）；括号剥离 `collect.py:107` 只剥匹配的圆括号对。
- 合成反例（实测）：
  - `is_correct("[0,1]", "(0,1)") == 1`（闭区间预测对开区间 gold 判对——假接受）；
  - `is_correct("[0,1]", "[0,1]") == 0`：`extract_answer` 的数字 token 正则把 `0,1` 连逗号一起抽出并剥掉括号，而 gold `[0,1]` 规范化保留括号——与 gold 完全相同的预测反而判错（假拒绝）；
  - `is_correct("(0,1]", "(0,1)") == 1`（半开对开判对）。
- 存档影响：对 `artifacts/gsm8k_audit/` 全部 14,400 条（36 harness × 400 任务）以端点敏感判分器重评：**0 翻转**（0 假接受、0 假拒绝）。仅 5/14400 条进入括号比较分支（4 值不等、1 长度不等），含 `[` 的 gold 仅 3 个且各成员预测均远离。故该缺陷是真实的判分器缺陷（已用合成例证明），但对冻结存档的 verdict 无可测影响。
- 现役判分器与存档 `official_correct` 完全一致：以当前 `is_correct` 重放 14,400 条，0 不一致（排除"判分器漂移"假设）。

## 2. K_eff 分子含 bare、分母不含 — CONFIRMED
- 代码：`experiment/gsm8k/metrics.py:43`（`vecs` 取自 `harnesses`，含 bare）与 `:70`（分母 `len(gen)`=35，不含 bare）。
- 实测：含 bare 33 个唯一结果向量（0.9429），剔除 bare 后 32 个（0.9143）；bare 的结果向量与全部 35 个生成成员向量均不同。
- `experiment/phase2/metrics.py:65` 与 `experiment/phase2/outcome_table.py:86-88` 是干净版本（分子分母同口径）。论文 `sec_crossdomain.tex:30` 引用 "K_eff 33/35 (0.94)" —— 受影响。

## 3. 生成成员准确率范围与 metrics.json 不一致 — CONFIRMED
- `artifacts/gsm8k_audit/metrics.json` `per_harness_acc`：生成成员范围 **0.6825–0.915**（最高 `gsm_kimi_s0_g2`=0.915，次高 0.865），bare=0.9375。
- 论文 `paper/latex/sec_crossdomain.tex:33-34` 写 "generated harnesses 0.68–0.87"。0.87 与 0.915、0.865 均不符（接近次高，疑为早期未完成运行的残留），该段其余数字（35 成员、400 任务、10.6% 分歧、union repair 76.0%、union harm 0.8%、headroom 4.75pp、bare 0.9375）与 metrics.json 相符。
- 独立重算（不经 metrics.py）从 run_*.jsonl 直接统计与 metrics.json 一致；每 harness 恰 400 条记录、无 (harness,task) 重复键（本轮实测 0 冲突），排除静默覆盖在本存档内实际发生。

## 4. union_harm 语义 — CONFIRMED（两个模块两种语义）
- `experiment/gsm8k/metrics.py:60-64`：`union_harm` = bare 正确且 **没有任何**生成候选正确的任务比例（0.8%）——即"全体候选联合失败"，是 union_repair 的补事件口径，不是"任一候选有害"，更不是 router harm。论文 cross-domain 段引用此口径。
- `experiment/phase2/metrics.py:66`、`analysis_primary.py:102`：`(m[:, ok].min(axis=0)==0).mean()` = bare 正确任务上 **存在至少一个**候选失败的比例——语义完全不同（数值必然大得多）。
- 风险：同名指标跨域混用两套定义；论文使用处未标明定义。诊断模块必须显式命名（`union_all_fail_rate` vs `any_candidate_fail_rate`）并停止共用符号。

## 5. MATH loader 弱身份/glob/覆盖/resume — CONFIRMED（机制属实；本轮存档未实际受损）
- 位置任务身份：`collect.py:202,209` `tid = f"{domain}#{100+i}"`，i 为 `split["tasks"][100:]` 的位置索引；身份依赖 split 文件顺序而非内容（本次核验中我自己的首轮 gold 映射就复现了这类错误的形态——位置错位导致 75% 假性不一致，改用内容校验 `db_id==subject` 后 14400/14400 全对）。
- glob 发现：`collect.py:186` `glob("gsm_*.py")`；`metrics.py:31` `glob("run_*.jsonl")`。
- 静默覆盖：`metrics.py:34-38` 跨文件 `dict.update`，后写覆盖先写。
- resume 重跑：`collect.py:201-203` 计算 `todo` 但从不使用；`:229` 对全部任务重新调用 harness，仅在写盘时丢弃已完成行——恢复执行会重复调用已完成的 LLM 任务。
- 本轮实际存档无重复键、无覆盖痕迹（见第 3 条），但这些机制是结构性风险，诊断入口必须用显式 manifest + 内容哈希替代。

## 6. insight 理论与反例未进入论文输入链 — CONFIRMED
- `experiment/revision/insight_theory_tests.py` 产出 `artifacts/revision_20260915/insight_analysis/insight_analysis.json`（构造反例 A/B、二动作恒等式、25 文件 SHA 清单）。
- 论文数值链：`main_revision_20260915_insight.tex` → `revision_numbers_20260915.tex`（由 `experiment/revision/render.py` 从 `artifacts/revision_20260910/{corrected_analysis,sensitivity,cost_audit,fingerprint,selection}.json` 生成）——**不含** insight_analysis.json。
- `w1_exact_counterexample`（61.26% 覆盖上界）已被引用（`sec_appendix.tex:235-249`）；insight 反例/恒等式仅以概念出现在 `sec_discussion_revision_20260915_insight.tex`，无数值引用。即：新理论内容"进了讨论、没进证据链"，当前版本不构成论文的定量贡献。

## 7. 原 gate 同时筛掉策略类别 — CONFIRMED（且论文已如实陈述）
- `experiment/phase2/conformance.py:285-293` `STRATEGY_CONTRACT` 把 `hint_guard`/`format_guard` 映射到 `"plain"` 场景，`run_scenario` 对 plain 恒返回 `NO_MECHANISM_declared`（`:245-246`）——prompt 级策略结构性不可通过，gated 臂 B/D 相对 ungated 臂 A/C 系统性排除该类别。
- 当前论文已承认：`sec_discussion_revision_20260915_insight.tex:13-16`"gate 同时排除允许的 prompt 策略，不能识别纯 verification 效应"；`artifacts/revision_20260915/FINAL_STATUS.md` 同。此线索在当前稿已处理，无需再改判。

## 汇总
| # | 线索 | 判定 | 需要的修复动作 |
|---|------|------|----------------|
| 1 | 区间开闭端点合并 | 机制属实，存档 0 翻转 | 判分器版本化 v2 + 全量重评（预期 0 变化，作为对照记录） |
| 2 | K_eff 分子分母口径 | 属实 | 修正并双报（33/35 与 32/35） |
| 3 | 准确率范围 0.87 | 属实（陈旧数字） | 论文改为 0.68–0.915 并注明来源 |
| 4 | union_harm 双语义 | 属实 | 显式改名 + 论文标注定义 |
| 5 | loader 弱身份/覆盖/resume | 机制属实，存档未受损 | 诊断入口用显式 manifest + 内容哈希 |
| 6 | insight 未入证据链 | 属实 | 论文重构时要么接入要么降级为讨论 |
| 7 | gate 筛掉策略类别 | 属实且已披露 | 无新动作 |
