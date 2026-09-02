# PAPER_PLAN — Behavior-Aware Harness Generation

> 生成时间:2026-09-02;**2026-09-03 判定后更新**。输入:PROBLEM_FREEZE.md v7/v8、
> artifacts/day2/DAY2_RESULTS.md。目标:ICLR 2027,主文 9 页。
> **判定结果:C6/D6 admitted(5.96/7.95pp)→ thesis 走"A 版协议修复 + F4 边界结果"混合版。**
> 全部占位符已回填;剩余工作 = 跨域加分实验(可选)、LaTeX 化、figures 精修、审稿回环。

## 0. 一句话贡献(候选,待 eval151 后定稿)

**Draft A(若 C/D 达标)**:我们证明 AI harness 生成器的失败模式是"句法多样、行为塌缩",
提出执行路径约束 + Harness IR 两类行为感知协议,使 AI 生成 population 的行为多样性
(union repair / oracle headroom)追平人工上界,并给出 harness-value prediction 的
precondition 检查表。

**Draft B(若 C/D 全不达标)**:我们对 AI-generated harness population 给出
"syntactic ≠ behavioral diversity" 的首个系统测量与失败模式分类,证明 headroom 真实存在
(人工 positive control 6.7pp)、而当前所有自动生成协议(3 Builder × 2 协议)均无法产出
行为多样性——并把"行为多样性前置检查表"确立为任何 harness-routing 工作的必过门槛。

## 1. Claims-Evidence 矩阵

| # | Claim | Evidence | 状态 | 章节 |
|---|---|---|---|---|
| C1 | AI 生成的 harness population 在代码层面多样、行为层面塌缩(syntactic ≠ behavioral) | Day-1:14 harness × 60 题,pairwise disagreement 3.5%(28/78 对=0),react 与 bare 逐字符相同(D=0) | ✅ | §4/§6 |
| C2 | 塌缩有明确的机制分类:纯 prompt 变体(6/12)/ 无效反馈(react 10/10 final SQL 与 bare 相同)/ buggy 多轮(散文当 SQL) | trace_audit.jsonl,artifacts/day1 | ✅ | §4 |
| C3 | 行为多样性的 headroom 真实存在(非 benchmark 饱和) | 人工 positive control:hpc×4,union repair 20.7%,oracle headroom 6.67pp(60 题;151 题复测 ⏳) | ✅(151 复测 ⏳) | §5 |
| C4 | free-form 长代码生成对弱 Builder 不可靠 | GLM-5.3-Flash B 臂 0/6 生成失败(builder_generate2) | ✅ | §6 |
| C5 | 行为感知协议(IR 臂:机制多样性由构造保证)可产生 ≥3 个非重复 fix sets | IR 6 个 smoke 通过;eval151 表现 ⏳ | ⏳ | §6 |
| C6 | gated free-form 协议 + 不同 Builder → population 质量随 Builder 能力变化 | C(qwen 6/6)/D(dsexp 6/6)eval151 指标 ⏳ | ⏳ | §6 |
| C7 | 行为多样性前置检查表(disagreement / union repair / headroom)是 value prediction 的必要条件 | 判定线预注册于 PROBLEM_FREEZE v7;两分支结果都支持该框架 | ✅(框架)/ ⏳(数字) | §7 |
| C8 | (条件性)unseen-harness value prediction 在达标 population 上可学 | LOHO 三层判据,仅当 C5/C6 达标才跑 | ⏳(可能不进论文) | §6.3/附录 |

## 2. 结构(empirical/diagnostic,9 页)

| § | 内容 | 页数 | 依赖 |
|---|---|---|---|
| 1 | Introduction:AI4AI harness 路线升温 → 但生成的 population 是否行为多样?→ 先测量、再修协议 → 贡献 3 条 | 1.5 | 无,可先写 |
| 2 | Related Work:harness/agent generation(TTHE、a-evolve、Self-Harness、JIT-Agent);harness 现象层(2607.18235、2605.26731、HELIX、STS、GRASP);behavioral diversity of LLM populations | 1.0 | 无,可先写 |
| 3 | Setup:Δ 定义、BIRD 域、frozen target、population 构建与冻结、四重切分(D_build∩D_eval=∅) | 1.0 | ✅ |
| 4 | 测量框架:三指标检查表 + trace audit 分类学(taxonomy 图) | 1.5 | ✅ |
| 5 | Positive control:4 个人工 harness,headroom 存在性 | 0.5 | ✅ |
| 6 | 行为感知生成协议 + 对照实验:三 Builder × 两协议(arm B/C/D)+ IR 臂 + 旧协议 A;对照表 | 2.0 | ⏳ |
| 7 | Discussion:对 harness routing/value prediction 的含义;precondition checklist 作为社区工具 | 1.0 | 部分 ⏳ |
| 8 | Conclusion + limitations | 0.5 | ⏳ |

图预算:hero 图(句法多样 vs 行为塌缩一图流)§1;taxonomy 图 §4;三条件对照条形图 §6;
IR pipeline 图 §6。表:主对照表 §6;检查表 §7。

## 3. 匿名与合规

- 双盲:不得出现作者/机构;代码匿名仓准备(appendix)。
- 预注册纪律:判定线(union repair ≥15-20%,headroom ≥5pp,≥3 非重复 fix sets)在
  PROBLEM_FREEZE v7 冻结,论文中如实引用,不事后修改。
- 负结果如实报告(用户纲领:完成 > 完美,结果如实)。

## 4. 写作顺序(不依赖 eval151 的先行)

1. §3 Setup、§4 测量框架(全 ✅);
2. §2 Related Work(引对手论文清单见 PROBLEM_FREEZE §1);
3. §1 Introduction 用 Draft B 措辞起稿(若 eval151 翻盘改 Draft A,改动集中在贡献句与 §6);
4. eval151 完成后:对照表 → 判定 → §5/§6/§7 定稿 + abstract。
