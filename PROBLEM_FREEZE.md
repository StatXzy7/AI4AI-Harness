# PROBLEM FREEZE — 2026-08-31

> 本文件自写入起为问题定义的冻结版本。改动需在文末 changelog 记录理由。
> 目标会议：ICLR 2027（abstract 2026-09-18，全文 2026-09-25 AOE，主文 9 页）

## 1. 冻结的研究问题

**Can we predict whether an unseen AI-generated harness will help a particular model
on a particular task, before executing it?**

核心概念：**Harness Marginal Value / Harness-Task Compatibility**

```
Δ(x, H, M) = Y(x, H, M) − Y(x, H₀, M) ∈ {−1, 0, +1}
  +1: raw wrong, harness correct   (repair)
   0: same outcome
  −1: raw correct, harness wrong   (harness-induced harm)
```

学习 V(x, H, M) ≈ Δ，在执行 H 之前预测。部署规则：干预当且仅当
`max_H V(x, H, M) > τ`，否则使用 raw model。

**关键区分（related work 的钉子）：**
- 与 STS (2604.06753)：STS 是 closed-set 分类（6 个固定人工范式，新范式需重新训练）；
  我们是 **open-set compatibility estimation**（对未见过的、由 Builder 新生成的 harness
  做 leave-one-harness-out 泛化）。
- 与 GRASP (2605.29668)：GRASP 的 gate 在**开发阶段**决定 skill edit 是否进入全局
  library；我们在**运行阶段**决定这个 query 是否接受某个 harness。
- 与 HELIX (2608.13951)：HELIX 证实 portfolio post-hoc union 比最佳单 harness 高
  58% coverage，但未实现 selector——我们实现它。
- 与 CF Search Routing (2607.05752)：方法学模板（counterfactual supervision →
  instance-level 事前路由），但动作空间是 {no-search, search, abstain}；
  我们的动作空间是 {raw, H₁…H_K}，且 H 是开放、可增长的。
- 与 TTHE (2607.08124)：TTHE 明确排除 per-query 机制（"persistent … rather than
  per-query retries"）。
- 与 JIT-Agent (2608.25593)：它是 per-task 在线**生成** harness 的训练模型；我们预测
  **已有** harness 的价值，不做生成。
- 与 Agentic Routing (2607.11399)：它在 harness state 内路由 **model**；我们路由 harness。
- ⚠️ HELIX 官方 GitHub roadmap 已明文列出 "Harness router: learn when to route a task
  to a fixed harness, a sibling portfolio, or a search pass"（**尚未实现**，2026-08-31
  核实）。novelty 保质期以周计——必须锁死 open-set / unseen-H 区别，这是护城河。

**统一 thesis**：Harness quality 不是标量 Q(H)，而是条件量 Q(H | x, M)。
此现象层正在被快速占领（2607.18235 "No Universally Superior Harness"、
2605.26731 "Harness Sensitivity Non-Monotone"），**只能作为 motivation，
论文必须由 open-set prediction 方法层扛**。

## 2. 两种推理 setting（都要报告）

1. **Pure pre-execution**：x, H（代码/描述/结构特征）, M → Δ。不运行 target。
2. **After-raw escalation**：x, H, M, raw 输出与置信度 → Δ。
   诚实标注：这属于 post-raw / pre-harness cascade，成本 = raw 一次 + 选中 harness。
   logprobs/置信度特征：pilot 选用支持 logprobs 的 OpenAI-compatible API provider；
   本地 vLLM（干净 logprobs + 同一 serving stack 的 model-scale 轴）推迟到 Phase C，
   **不是启动条件**。

## 3. 四重数据切分（写代码前冻结）

| 切分 | 用途 | 占比 |
|---|---|---|
| D_A | Harness construction（Builder 可见） | 5% |
| D_B | Value predictor 训练 | 25% |
| D_C | 阈值/校准/dev | 10% |
| D_D | **Locked final test** | 60% |

约束：D_A ∩ D_B ∩ D_C ∩ D_D = ∅；Builder 永远看不到 D_B/C/D；
所有 harness 在 D_A 上开发后立即冻结存档；D_D 只在最后评估一次。
ToM 基准较小，若 D_D=60% 导致 predictor 训练不足，允许改为 10/30/10/50，
但必须在任何实验开始前定死并写入 changelog。

## 4. Harness 规模

- ≥ 2 个 Builder 配置 × 3 seeds = **6 个起，目标 8–12 个**（LOHO 每折需要一个 held-out
  harness，太少则 LOHO 方差不可信）。
- Harness 在 D_A 上构建，构建后冻结；**不**为 predictor 重新调优 harness。

## 5. Kill Criteria（72h pilot，三层缺一不可）

- **L1 Headroom**：OraclePortfolio − BestFixed ≥ 5pp（portfolio 互补性存在）。
- **L2 Closed-set 可学**：closed-set router − BestFixed ≥ 2pp（instance 级信号存在）。
- **L3 Open-set 泛化（生死线）**：Leave-One-Harness-Out 的 unseen-harness value
  predictor > BestFixed 且 > task-only router（STS 复现线），并显著降低 P(Δ=−1)。
  LOHO 崩到 chance 水平 → **砍题或降级为 closed-set 分析**（不投）。

Pilot 阶段只看效应量：pp gain、bootstrap CI、oracle capture ratio、harm reduction、
LOHO 曲线。**McNemar / 多重校正只在 locked D_D 上做一次**，pilot 不得触碰 D_D。

## 6. 必做的 baseline 矩阵

| 基线 | 成本 | 角色 |
|---|---|---|
| BestFixed harness | C | 下界锚点 |
| Task-only router（STS 复现） | C | closed-set 对照 |
| Confidence gate（raw logprob 阈值） | 2C（raw+H） | cheap dynamic 对照 |
| Majority vote over K harnesses | KC | **high-cost ensemble** 对照（不是 cheap） |
| Self-consistency@K on raw | KC | cost-matched 对照 |
| Oracle selector | KC | 上界 |

## 7. 实验域（v2：API-first，实验独立于原论文代码）

- **Experiment A（Day-0，零 API 成本）**：`external/fragility-grid`——12 模型 × 26 harness
  配置 × 3679 题的逐题对错位（48 个 JSONL，含 gold 与 top-2 likelihood margin 特征，
  MIT 许可，CPU 秒级复现）。跑 LOHO value-prediction sanity：验证数学形式可学性。
  config-level harness，不能作主实验，只作 sanity 与 motivation 图。
- **Experiment B（pilot 主战场）**：TTHE/text_to_sql（BIRD，SQLite，程序化判分，无 Docker，
  执行快）。TTHE 原生支持任意 OpenAI-compatible endpoint（config.example.yaml 即
  DeepSeek 示例），且自带离线 demo。Harness 种群：TTHE optimize 循环 G 个 branch 的
  harness + 自有 Builder 在 D_A 上生成的 HarnessBase 子类。
- **Experiment C（跨域）**：TTHE/ds1000 → livecodebench，证明非单域现象。
- **Experiment D（可选外部验证）**：SWE-bench Verified 子集（TTHE 标注 heaviest，需
  Docker + mini-swe-agent）；Strong-to-Weak 的 ToM（仅当原作者回复代码）。
- HarnessBench：前三个成立后再考虑（无 LICENSE，Windows 需 WSL）。

Target 模型：Phase A/B 全 API（一个 cheap/mid + 一个 stronger，OpenAI-compatible；
logprobs 可得者优先）。Phase C 补本地 Qwen3 family（cross-model 泛化 + 干净 logprobs 轴）。
Builder：API 强模型，预算 60% builder / 20% judge & error analysis / 20% final repeats。
**原论文（2608.12307）代码降为可选项**：回复则并入 D，不回复不影响主线；
本文凭 A/B/C 已独立成文。

## 8. 与既有仓库的对接

- `external/TTHE`：harness 接口（harness_base.py）、种子 harness（bare/react）、
  evaluator、bridge 直接复用于域 2；原生 OpenAI-compatible API 支持（v2 主底盘）。
- `external/fragility-grid`（MIT）：2608.21382 官方数据发布，Experiment A 数据源。
- `external/a-evolve`：Builder 侧管线可选底座。
- `external/harness-bench`：域 4 候选（无 LICENSE，谨慎）。
- `external/Awesome-AI4AI`：每周领域追踪。

## 9. 时间线（倒排）

| 日期 | 必须完成 |
|---|---|
| 09-01 ~ 09-03 | Day-0：fragility-grid LOHO sanity（零 API）；TTHE 离线 demo + API endpoint 跑通；BIRD outcome matrix（2 API target × 6-10 harness × D_B/C） |
| 09-03 晚 | 三层 kill criteria 判定，GO/Pivot/Kill 书面记录 |
| 09-04 ~ 09-08 | value predictor + LOHO + baseline 矩阵 |
| 09-09 ~ 09-12 | ToM 域完整化、跨 target 泛化曲线、cost 分析 |
| 09-13 ~ 09-16 | 消融、figures、D_D locked test 一次性评估 |
| 09-18 | ICLR abstract 提交（之后不可再加作者） |
| 09-18 ~ 09-23 | 9 页全文 + appendix + 匿名代码 |
| 09-25 | 全文提交 |

**止损条款**：若 09-05 pilot 未达 L1，或 09-09 L3 无望，转投 ICML 2027（1 月底），
同一工作做完整版。

## Changelog

- 2026-08-31 v1：初版冻结。novelty 搜索确认 open-set unseen-harness value prediction
  无人占据；现象层（conditional harness utility）已有两篇邻近工作，降级为 motivation。
- 2026-08-31 v2：**API-first 决策**——模型不本地部署，TTHE 原生支持 OpenAI-compatible
  endpoint（本地核实 config.example.yaml + 离线 demo 命令），pilot 0 GPU 可启动；
  5090 推迟到 Phase C（cross-model 泛化 + 干净 logprobs）。原论文代码降为可选。
  新增对手核实：JIT-Agent (2608.25593，per-task 生成型，非撞题)、Agentic Routing
  (2607.11399，路由 model，非撞题)；**HELIX roadmap 已列 Harness router（未实现），
  保质期警告**。Experiment A 改为 fragility-grid Day-0 免费验证（已克隆
  NikolaTesla-007/fragility-grid，48MB，含 margin 特征）。实验重组为 A/B/C/D 四层。
- 2026-08-31 v3：**Day-0 结果（GO 状态降级为 CONDITIONAL）**——L1 PASS（oracle
  headroom 20.7pp）；L2 MARGINAL FAIL（policy +1.13pp < 2pp）；**L3 FAIL**（harness
  结构表征在 task-only 之上 LOHO 增益 ≈ 0.0003 AUROC）。机制：config 级 harness 家族化
  （4-5 个家族、家族内行为近相同）、无正平均 offset config、逐 item 翻转由 item 脆弱性
  主导。详见 `artifacts/day0/DAY0_RESULTS.md`。**后续门（gate）**：假设的唯一存活检验是
  executable-harness regime（TTHE/BIRD 真 API outcome matrix 上重跑 LOHO，
  `experiment/tthe_collector.py` 已就绪待 API key）；若 harness 表征增益仍 ≈0 或
  policy gain < 2pp → 正式砍题。拿到 API key 前不投入写作。TTHE mock 冒烟已通过
  （管线 + harness population 21 个 + 统一 outcome schema 验证，
  见 `artifacts/day1/TTHE_SMOKE_TEST.md`）。
- 2026-08-31 v4：**Day-1 executable-harness 管线打通 + 塌缩发现**。BIRD 接入、TTHE 修复
  （claude 路径/proposer 模型/stdin/killpg）、population 14 个可执行 harness、并行收集器、
  840 行 outcome matrix。**builder=target ⇒ harness 行为塌缩**（Δ 98.2%=0，top-5 union
  修复率 0.0，headroom 仅 3.3pp）——per-item 互补性不存在，LOHO 无法检验。与原论文设定
  的关键差异：原论文 Builder≫Target。**决定性实验（次日）**：DeepSeek 当 Builder
  （builder≠target）重生成 population，检验 (a) 行为多样性是否出现 (b) LOHO 三层判据。
  若无信号 → 砍 open-set value prediction，转聚合命题"AI4AI 迁移需要多大 Builder–Target
  差距"。详见 `artifacts/day1/DAY1_RESULTS.md`。
- 2026-08-31 v5：**behavioral-collapse 诊断完成（决策树 Step 1+3）**，撤回 v4 的因果表述
  （"builder=target ⇒ collapse"不成立：TTHE/Self-Harness 反例）。事实链：AI 生成 population
  3.5% 分歧、28/78 对零分歧、union 修复 7.7%、headroom 3.3pp；trace audit 分层定位（6/12 纯
  prompt 变体、react 反馈无效、唯一多轮实现有 bug）；**人工 positive control headroom
  6.67pp 过线、策略真互补**——domain 没问题，瓶颈在生成协议（证据太少/单轮/无控制流约束/
  无执行路径验收）。明日起：修生成协议 → 三 Builder 条件对照 → headroom≥5pp 的 population
  上才跑 LOHO。样本量扩至 100-150 题。详见 `artifacts/day1/DIAGNOSIS.md`。
- 2026-08-31 v6：采纳"前提条件优先"框架：harness quality = f(builder capability, task
  signal, feedback, runtime freedom)，四变量均已有测量锚点（signal 饥饿 = proposer 每轮
  3 题 + label-free proxy 噪声；runtime freedom 受 timeout 墙/audit 约束）。DeepSeek
  条件已验证连通（deepseek-chat / deepseek-v4-pro，零采购成本）。**预注册判定线**：
  三 Builder 对照（150 题）中 union repair ≥20% 且 headroom ≥5pp 的条件才进 LOHO；
  全部不达标则主 finding = F1+F2。LOHO 继续暂停至 population 达标。
- 2026-09-01 v7：**论文定位正式调整（用户批准）→ Behavior-Aware Harness Generation**。
  主问题："AI 生成的 harness population 是否真的行为多样，以及如何强制其多样"；
  value prediction 下游化为多样性达标后的应用层。实验两臂（grill 批准）：
  (1) gated free-form 臂（机制必须进控制流 + 执行签名验收）；
  (2) SQL Harness IR 臂（spec → deterministic compile → HarnessBase，
  `experiment/harness_ir.py` + `experiment/specs/*.json`，机制多样性由构造保证）。
  评测集 151 题（card_games 121 + formula_1 30，分层，D_build∩D_eval=∅，
  `experiment/split_eval151.json`）。Builder 条件：GLM-5.3-Flash（B 臂 0/6 生成失败——
  free-form 长代码生成能力不足，本身是 F1 证据）、Qwen3.8-Flash、
  DeepSeek-V4-Flash-Vision-Exp（paratera ziyang key，`experiment/.env_tthe_ziyang`）。
  预注册判据不变：union repair ≥15-20% + oracle gap ≥5pp + ≥3 个非重复 fix sets
  才进 LOHO。
- 2026-09-03 v8：**Day-2 判定完成（151 题矩阵，30 harness，判分 bug 修复后有效数据）**。
  多样性门槛：C6(Qwen gated free-form) 与 D6(DSexP gated free-form) **admitted**
  （headroom 5.96/7.95pp，repair 21.6/24.3%，6 个 distinct fix sets）；A6 旧协议 4.64pp
  差 0.36pp 未过；IR 臂 3.97pp 未过；人工对照 151 题上 repair 14.9% 卡线（60 题的 20.7%
  系小样本高估）。**F3 成立：行为多样性可由 trace-gated 生成协议拉起，A<B(0/6)<C<D。**
  LOHO 三层：L1 PASS；L2 MARGINAL FAIL；**L3 FAIL**（harness 表征增益 ≈0.0007 AUROC；
  policy vs best-fixed：D6 -3.4pp、C6 +0.86pp CI 含 0、ALL24 -0.86pp CI 含 0）——
  开放集 value prediction 在 admitted population 上依然不学，与 Day-0 config-level
  失败构成决定性复现。论文按 v7 定位收束为 Behavior-Aware Harness Generation：
  F1 塌缩测量 + F2 headroom + **F3 协议修复（主结果）** + F4 诚实负结果（多样性必要
  非充分）。数据与判定详见 `artifacts/day2/DAY2_RESULTS.md`。统计备注：预注册阈值
  下 IR/人工的 borderline 未做事后放宽，原样报告。
