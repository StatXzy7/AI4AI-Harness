# Isolated insight revision audit (2026-09-15)

## Initial verdict

这轮是科学边界的推进，不是已完成的 usefulness 闭环：稿件现在明确区分 source/trace/outcome diversity、事后 oracle 与运行前选择，且加入了可执行反例和条件选择价值恒等式；但现有数据没有冻结的 selector、成本匹配 clone control 或独立重复上的净优势验证。因此 insight 是可检验的测量/设计命题，usefulness 仍未估计。当前论文 verdict：**4/10，not ready**。

## Claim--evidence ledger

| 主张（当前稿原文） | 证据位置/版本 | 类型 | 完成度 | 尚缺判断 |
|---|---|---|---|---|
| source code diversity 不等于 outcome diversity | `sec_intro_revision_20260915_insight.tex`; Phase-I matrices | 描述/测量 | 已完成（发现性） | 更广 builder/domain 的外推仍未知 |
| mechanism 可能 absent、untriggered 或 broken | Phase-I trace inspection; `sec_phase1` | 描述/诊断 | 已完成（发现性） | 不是总体发生率或因果效应 |
| 原 gate 的 D-A contrast 无清晰改善 | `artifacts/phase2/analysis_primary.json`; corrected revision numbers | 统计/干预 | 已完成为 post-review reanalysis | 不是 repaired-gate 或 pure-verification 估计 |
| gate main effect 不是 verification 的独立因果效应 | `sec_phase2.tex`; `analysis_factorial.json` | 逻辑/因果边界 | 已建立 | 需要允许 prompt strategies 的受控桥接 |
| one-run oracle headroom 不等于 stable complementarity | R2/R3 repeats; same-code diagnostic in `sec_results_revision_20260915.tex` | 描述/机制边界 | 已由反例和不稳定性支持 | balanced cost-matched clone control 未完成 |
| residual-error coverage 是运行前选择原则 | `w1_selection.json`, `w1_headroom.json` | 设计假说 | 仅定义/探索性 | frozen selector、held-out policy utility、repair−harm 与成本 |
| 预测、稳定、cost-effective 的优势可被识别 | 当前无独立 selector 结果 | 部署/泛化 | 未完成 | 需可见 Z、独立 repeats、held-out tasks 和成本字段 |
| MATH-500 中出现同一测量边界 | `revision_numbers_20260915.tex`; writing validation | 描述/跨域 | 已完成为 one-seed probe | 无 clone/repeat/selector，不能作稳定性结论 |

## 新旧贡献边界

旧 W1 的 `div-only` 已是同一候选池、同一 baseline 和任务划分下的 greedy oracle-coverage 基线；本轮没有另造同义算法。它的结果是 post-hoc、按数据库一半切分的探索性 held-out 描述，不能升级为选择器收益。新增内容是把“覆盖更多一次性错误”与“运行前可识别的净优势”分开，并给出最小反例与恒等式。

## 数据覆盖和单位

机器可读覆盖表见 `insight_analysis/input_inventory.csv`，由冻结的 `primary_input_manifest.json` 和 `bc_input_manifest.json` 逐文件读取，25 个文件的 manifest SHA-256 前 16 位全部匹配。记录包含 `(harness_id, task_id, repeat)`、`no_cache`、target、`latency_ms`、`n_llm_calls` 和 `n_execs`；provider/cost 金额字段在这些 JSONL 中为空。主 AD/BC 结果均为 repeat 0、cache-on，并采用已有 `completeness_report.json` 的 canonical first-write 冲突规则。R2/R3 repeat 数据是独立的稳定性诊断，不能与主结果拼接成平衡的效用估计。

## 结果解释边界

- 绝对 oracle、best-fixed、开发集 fixed 和 repair−harm 必须用同一任务与 baseline 报告；headroom 是 oracle 减 best-fixed，不是实际 routing gain。
- `C_Z` 是知道条件期望时的信息约束最优值，不是当前学习器已经实现的收益；计入成本后应改用净效用并扣除获取 Z 和路由开销。
- “击败开发集选出的 fixed”只说明相对于该选择流程，不能说明击败未知真实最优 fixed。
- 当前资料不足以区分执行不稳定、特征不可识别、估计精度不足和学习器能力不足；不把失败归因于单一原因。
