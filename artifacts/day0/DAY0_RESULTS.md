# Day-0 Results — Fragility Grid Sanity Experiment

日期：2026-08-31　脚本：`experiment/day0_sanity.py`（1210s, CPU only）
数据：`artifacts/day0/outcome_matrix.parquet`（1,103,700 行 Δ 记录）+ `day0_stats.json` + `loho_results.json`

## 实验设置（回顾）

- H0 = `gen|letter_plain|p0`（标准 MCQ 配置）。Δ(x,H,M)=Y(x,H,M)−Y(x,H0,M) ∈ {−1,0,+1}。
- LOHO：25 个非参照 config 逐一 held-out；tau 与 best-fixed 在 tune 半区（20% item）选择，
  eval 半区（80%）报告。预测特征不含任何 config 身份信息（open-set 协议）。
- Setting A = question TF-IDF + benchmark + model one-hot + harness 结构特征（scoring/fmt/
  gold 位置/排列）；Setting B = A + ll_margin（after-raw，单独报告）。

## 数据事实（A2）

| 统计 | 值 |
|---|---|
| 每 config 准确率范围 | 0.456（ll\|cloze_question）～ 0.752（gen\|letter_plain\|p1） |
| **Best fixed** | gen\|letter_plain\|p1 = **0.7520** |
| **Oracle portfolio** | **0.9587**（headroom **20.7pp**） |
| Δ 分布（vs H0） | 0: 75.3%，**−1: 18.8%**，+1: 5.9% |
| 存在跨 config 翻转的 item | **85.1%** |
| config offset 结构 | 家族化：letter_plain ≈ 0 / letter_paren ≈ −6.5pp / instruction ≈ −10.5pp / digit_labels ≈ −25pp / cloze(ll) ≈ −28pp；家族内排列差 ≤ ±0.5pp |
| top-8 config 的 union 修复率 | 仅修复 H0 错误的 15.8%（同家族 config 高度相关） |
| 正 offset 的 config 数 | **1 个，且仅 +0.03pp**（没有任何 config 平均优于 H0 到可用程度） |

## L1 / L2 / L3 判定（冻结标准 §5）

### L1（portfolio headroom ≥ 5pp）：**PASS**
Oracle 0.9587 vs BestFixed 0.7520 → **20.7pp**。互补性巨大、85% item 存在翻转。

### L2（closed-set policy ≥ 2pp）：**MARGINAL FAIL**
- closed-set AUROC（harness-id 可见）：0.676 vs task-only 0.661（+1.5pp，harness 身份有信息）。
- 但 LOHO policy 端到端只拿到 **+1.13pp**（CI95 [0.76, 1.51]），低于 2pp 线。

### L3（unseen-harness 泛化，生死线）：**FAIL**
| 模型 | LOHO AUROC (Δ>0) |
|---|---|
| Setting A（task+model+harness 结构） | 0.7089 |
| task-only 对照 | 0.7086 |
| harness-only | 0.6762 |
| Setting B（+ll_margin） | 0.7097 |

**harness 结构表征在 task-only 之上的增益 = 0.0003 AUROC（≈零）。** Policy +1.13pp
几乎全部来自 item 脆弱性预测（task 特征），harness 侧贡献可忽略。harm rate on
intervention 15.6%（基线患病率 18.8%）——有轻微避开坏 config 的作用，但不是可发论文的量级。

## 为什么失败（机制诊断，重要）

1. **26 个 config 实际上是 4-5 个家族**。家族间 offset 巨大（0 ~ −28pp），家族内
   排列几乎无差别。open-set 预测器能从结构特征学到"digit_labels 家族很糟"，
   但这只能带来 harm avoidance，不能带来 repair 选择。
2. **没有任何 config 有正的平均 offset**（最多 +0.03pp）。选择问题的"平均收益"上限
   接近零——20.7pp headroom 全部藏在逐 item 翻转里，而翻转概率由 item 本身的
   脆弱性主导（A≈T 的根源），config 身份对"这个 item 在这个 config 下会不会翻转"
   的边际信息≈0。
3. ll_margin（after-raw）几乎不增加（+0.001 AUROC）：item 脆弱性从文本特征已经
   基本可预测。

## 结论与建议

**按冻结判据：L3 FAIL。** 在 config 级 harness 上，"从 harness 结构预测其对未见
config 的边际价值"这一命题**不成立**——不是模型不够强，而是该 regime 下没有可预测的
harness 条件结构（家族 offset 可学但只够 harm-avoidance；逐 item 翻转与 config 身份无关）。

按指令要求，**不建议在此结果上继续堆复杂模型**。给出两条诚实路径：

1. **唯一值得的挽救检验（gate 后再花钱）**：executable harness regime（TTHE 候选种群：
   voting / repair loop / self-verify 等，行为差异远大于 prompt 格式差异）。该 regime 下
   (a) 存在正平均 offset 的 harness（voting/repair 通常平均更好），(b) harness 行为
   差异更大。L3 检验必须在真 API + BIRD outcome matrix 上重跑（`tthe_collector.py`
   已就绪，只差 API key）。**若 executable-harness LOHO 中 harness 表征仍无增益 →
   正式砍题**，按 §9 止损条款转 ICML 2027 或放弃。
2. **若 TTHE 侧也失败**：本项目放弃 "open-set value prediction" 提法；残值资产
   （outcome matrix 工具链、probe-offset 方法思想）可并入其他方向。

一句话：**Day-0 用零成本买到了一个真实的负结果——它杀死的是"config 级 harness"版本
的假设，并给出了 executable-harness 版本必须证明的具体指标（harness 表征 LOHO 增益
> 0 且 policy gain ≥ 2pp）。** 在拿到 API key 跑出 BIRD 矩阵之前，不应再投入任何写作时间。
