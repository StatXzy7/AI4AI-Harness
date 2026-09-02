# DAY-2 RESULTS — 151 题 outcome matrix 与预注册判定

日期:2026-09-03 凌晨(矩阵收集 09-02 晚启动)。
产物:`artifacts/outcomes/tthe_eval151_matrix.parquet`(4530 行 = 30 harness × 151 题)、
`artifacts/day2/eval151_comparison.json`(+ `_ci.json`)、
`artifacts/day1/LOHO_RESULTS_{D6,C6,ALL24}.json`、`artifacts/day2/fig_hero.png`/`fig_taxonomy.png`。

## 0. 数据有效性

- 判分 bug(progress_handler)修复后 bare 151 题 acc=0.510,与 Day-1 60 题锚点(~0.567)同量级;
- 冒烟 12/12 新 harness 无异常;全 population best-fixed 0.583,oracle-any 0.695。
- ⚠️ 数据卫生备注:eval151 中 24 题与 Day-1 的 60 题重叠(已在 Limitations 披露);
  A 臂 6 个候选只用 36 个不重叠题选择(a6_selection.json)。

## 1. 预注册对照表(151 题,判定线:repair≥15% + headroom≥5pp + ≥3 distinct fix sets)

| Population | disagree | union repair [CI95] | headroom pp [CI95] | distinct fixsets | **判定** |
|---|---|---|---|---|---|
| A6 旧协议(proposer) | 7.0% | 24.3% [.149,.347] | 4.64 [1.3,8.0] | 5 | ❌(headroom 差 0.36pp) |
| B GLM free-form | — | 0/6 生成失败 | — | — | n/a(F1 证据) |
| **C6 Qwen free-form** | 11.1% | 21.6% [.125,.310] | **5.96** [2.0,8.6] | 6 | ✅ **admitted** |
| **D6 DSexP free-form** | 11.2% | 24.3% [.148,.346] | **7.95** [4.0,11.3] | 6 | ✅ **admitted** |
| IR6 编译 | 8.2% | 16.2% [.083,.253] | 3.97 [1.3,7.3] | 6 | ❌(headroom) |
| 人工对照(4) | 8.9% | 14.9% [.071,.237] | 7.28 [3.3,10.0] | 4 | ❌(repair 恰差 0.14pp) |
| ALL24 跨协议混合 | 10.3% | 37.8% [.268,.488] | **11.26** [6.6,15.9] | 23 | ✅(分析用) |

**主 finding F3 成立:行为多样性是可以被生成协议拉起来的。**
趋势 A(旧协议,4.64pp)< C(5.96pp)< D(7.95pp);B(GLM)在生成可靠性处就断了。
协议与 Builder 能力都重要:同一个 gated 协议,弱 builder 产出不了代码;
旧协议(无 trace 门禁)产出的 population 头部太集中(one candidate 0.583 独大 → headroom 挤掉)。
人工对照 60 题 → 151 题 repair 20.7%→14.9%:60 题样本量高估了(诊断时已预警),
151 题口径下人工也卡线——**"人工轻松达标"的叙事要修正为"人工也只在 headroom 轴强"**。

## 2. LOHO 三层判据(仅对 admitted populations,PROBLEM_FREEZE §5)

| 层 | 结果 | 判定 |
|---|---|---|
| L1 headroom | D6 7.95pp / C6 5.96pp / ALL24 11.26pp | **PASS** |
| L2 closed-set | harness-id AUROC 0.475(D6)/0.575(ALL24);无 ≥2pp policy 证据 | **MARGINAL FAIL** |
| L3 open-set(生死线) | harness 表征在 task-only 上增益:D6 +0.0007 AUROC(≈0);policy vs best-fixed:D6 **-3.4pp**、C6 +0.86pp(CI 含 0)、ALL24 -0.86pp(CI 含 0);vs H0:ALL24 **+6.9pp、干预 harm=0%** | **FAIL** |

**结论:开放集 value prediction 在行为多样的 population 上依然不成立**(与 Day-0 在
config-level 上的失败一致——现在是在 admitted population 上的决定性复现)。
但有一个部署相关的正结果:ALL24 上 predictor-as-gate 对 H0 +6.9pp 且零 harm——
它从不引入 harness-induced harm,只是抓不到超过 best-fixed 的空间。

## 3. 论文定位最终落定(v7 框架内,无需再改 thesis)

论文 = **Behavior-Aware Harness Generation**(PAPER_PLAN Draft A 变体):
- F1 塌缩测量 + T1/T2/T3 分类学(§4);
- F2 headroom 存在性(§5,151 题复测 7.28pp);
- **F3(新主结果):trace-gated 生成协议 + builder 轴对照,首次把 AI 生成 population
  拉过预注册多样性门槛(2/3 builder 达标)**(§6);
- F4(诚实负结果):多样性是路由的必要条件而非充分条件——开放集 value prediction
  仍无可学习信号(§7,L3 全线 FAIL 如实报告)。

## 4. 待办

1. 论文占位符回填([R1][R2][F3]、§6.0 表、abstract Draft A 变体、§7 两处、§8);
2. `/auto-review-loop` 送审(Codex);
3. 剩余时间(至 09-25):Exp C 跨域(TTHE/ds1000)是加分项;figures 精修;
   LaTeX 化 + 匿名仓。
