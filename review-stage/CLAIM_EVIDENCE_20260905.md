# CLAIM–EVIDENCE INVENTORY — 2026-09-05 (prompt-1 revision)

状态标记:**supported**(证据齐备可入稿)/ **discovery-only**(Phase-I 实测,只作发现不作确认)/ **pending**(Phase-II 采集/分析未完成)/ **retracted**(协议已撤回,必须从正文移除)。

| # | 主张 | 证据 | 状态 | 论文位置 |
|---|---|---|---|---|
| C1 | Day-1 生成候选句法多样、行为塌缩:12 候选 66 对中 21 对完全一致,平均分歧 3.8%;含 baseline 的 14 harness/91 对中 36 对一致,token 相似度与结果分歧 Spearman ρ=−0.01 | `fig_hero_data.json`(12 候选);`fig_phenomenon` 图 + `fig1_phenomenon_data.json`(14 harness);`tthe_bird_matrix.parquet` | supported(两口径并列,图注说明) | §1, §3, Fig.1 |
| C2 | 塌缩机制三分类 T1/T2/T3(描述未实现 6/12;反馈无因果路径 react 10/10;多轮实现损坏 1/12) | `trace_audit.jsonl`, day-1 | discovery-only | §3 |
| C3 | 任务域存在 routing headroom:人工对照 60 题 6.67pp,151 题 7.28pp [3.3,10.0];repair 151 题 14.9% | `tthe_bird_positive_control.parquet`, eval151 矩阵 | discovery-only(对照设计于查看 day-1 trace 之后,存在性证明而非盲估计,已披露) | §3.4 |
| C4 | ~~旧协议塌缩是 builder-independent(40 候选 780/780 全同)~~ | 40 个候选 SHA256 = bare 源码 | **retracted**(PHASE2_PROTOCOL §9:同码同结果是同义反复,重新分类为 M0 generation null;只可作生成失败报告,不可作行为塌缩或 builder 归因证据) | 原 §1/§6.4 — 移除,改为 M0 报告 |
| C5 | Phase-I 下 strategy-forced 群体点估计过线(C6 5.96pp/D6 7.95pp),旧协议 A6 4.64pp 未过;接受率 GLM 3/8 < Qwen 7/8 < DS 8/8 | eval151 矩阵 + 生成日志(09-03 后);C/D 09-01 运行无逐次日志(已披露) | discovery-only(两嵌套对照,无法分离主效应;smoke≠严格 conformance gate;预算记录不完全) | §3.5 |
| C6 | LOHO/开放集价值预测未超越最佳固定 harness;task-held-out AUROC 0.512≈chance;+6.9pp 零诱导 harm 仅在 24-harness 池的任务重叠设定下 | `loho_exec.py` 输出, `task_split_D6_v2.json` | discovery-only,须限定到已测 predictor/split,不得写成部署保证 | §5 |
| C7 | Phase-II 主问题:等预算下 strategy forcing + conformance gate 是否提高可路由空间 | 冻结协议 `PHASE2_PROTOCOL.md`,锚点 `PROTOCOL_FREEZE.txt` | 方法可写,结果 **pending** | §4 |
| C8 | 因子次要(gate/strategy 主效应+交互,core-400 同题集) | 同上 | **pending** | §4.3, §4 表骨架 |
| C9 | 生成可靠性分解 R_artifact/R_contract/R_fidelity(Arm E) | 生成日志(E 臂 1 run dev-side) | **pending**(三率框架可写) | §4.2 |
| C10 | headroom 随 K 单调增长 | — | **retracted**(数学错误:单调的是 oracle accuracy;反例:加一个全对 harness 使 headroom→0。改为 matched-K 控制且不假设单调) | 原 §6.3 — 已修 |
| C11 | 未过 5pp checklist ⇒ router 至多找回最佳固定 harness | — | **retracted**(4pp 群体仍可能优于最佳固定选项;阈值是操作描述,不是必要条件) | 原 Discussion — 已修 |

## 数值一致性口径

- **候选对**(12 生成候选,C(12,2)=66):相似度均值 0.1431(hero 数据),21/66 全同,分歧 3.8%。
- **全群体对**(14 = bare+react+12 候选,C(14,2)=91):token-ratio 相似度均值 0.190,36/91 全同,分歧 3.3%,ρ=−0.01(fig_phenomenon)。
- 两口径都真实;图用全群体对,图注与正文明确说明包含 baseline;正文引用候选对数字时标注"候选对,不含 baseline"。
- ρ 的显著性:91 对共享 harness,非独立样本;图注只陈述 ρ 点值,不做独立性 p 值推断。
