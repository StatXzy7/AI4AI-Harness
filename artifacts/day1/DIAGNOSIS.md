# Behavioral-Collapse 诊断报告（Day-1 晚间追加）

日期：2026-08-31 下午　前置：`DAY1_RESULTS.md`　新产物：
`population_diagnosis.json`、`trace_audit.jsonl`、`positive_control_diagnosis.json`、
`experiment/trace_audit.py`、4 个 `hpc_*.py` 人工 harness

## 0. 结论修正（采纳外部评审）

Day-1 报告中"builder=target ⇒ collapse，AI4AI 迁移需要认知差"的因果表述**撤回**。
反例：TTHE 本身（solver/proposer/judge 同一 frozen LLM）有效；Self-Harness (2606.09498)
同模型自改进有效。当前可支持的表述仅为：

> 在 GLM-5.3-Flash + TTHE/BIRD + 当前 proposer protocol 下，AI 生成的 harness population
> 出现 behavioral collapse：syntactic diversity ≠ behavioral diversity。

## 1. Population 诊断（AI 生成，14 harness × 60 题）

| 指标 | 值 |
|---|---|
| pairwise outcome disagreement | 平均 3.5%，最大 13.3%，**28/78 对完全零分歧** |
| union repair of bare errors | 2/26 = 7.7% |
| oracle headroom | 3.3pp |
| react vs bare | **D = 0.0**（完全一致） |

## 2. Trace Audit（5 harness × 10 题的执行轨迹）

关键分层发现——"代码不同"分三种情况：

1. **6/12 候选是纯 prompt 变体**：执行路径与 bare 完全相同（每题 1 次 LLM 调用、0 次
   execute）。docstring 声称的机制根本不存在于控制流中（例：cap-tokens harness 只改了
   prompt 措辞和输出上限）。
2. **react 有执行反馈但零行为差异**：10/10 题 final SQL 与 bare 逐字符相同。ReAct 的
   execution feedback 在 SQL 任务上不改变答案。
3. **唯一实现多轮执行的候选有 bug**：repair 循环把散文文本当 SQL 返回（final SQL 是一段
   英文句子），把 bare 原本答对的题改错，净效应为负。

## 3. 人工 Positive Control（决策树 Step 3）

人工写 4 个执行路径强制不同的 harness（execute-repair / vote3 / schema-linking /
hint-first），同一 60 题、同一 target：

| 指标 | AI 生成 population | 人工 positive control |
|---|---|---|
| pairwise disagreement | 3.5% | **8.6%** |
| union repair of bare errors | 7.7% | **20.7%** |
| oracle headroom | 3.3pp | **6.67pp（过 5pp 线）** |
| 各策略独有修复 | ≈0 | repair/schema/hint 各 3 个，**真互补** |
| regression | 7（union） | 4（union） |

## 4. 决策树判定

```text
Step 1 (trace audit):  execution 路径确实不同（至少部分 harness）——不是 runtime 全同
Step 2 分支:           当前 GLM builder + 当前 proposer protocol → 生成失败（无行为多样性）
Step 3 (positive control): BIRD/GLM/60 题本身有 ≥5pp headroom —— domain 没问题
```

**判定：问题定位在"AI Builder 生成协议"，不在 domain，也不在（尚未检验的）Builder 能力。**
具体嫌疑：proposer 证据量太少（cap=3 题）、单轮编辑、无"必须改变控制流"的约束、
无执行路径多样性验收。

## 5. 明天的实验序列（顺序执行）

1. **修生成协议**：给 Builder 8 道例题 + 显式要求"执行路径必须与 bare 不同（≥2 次 LLM
   调用或 ≥1 次 execute）" + 把 trace-audit 加入自动验收（执行路径与 bare 相同的候选
   直接拒绝重生成）。
2. **三 Builder 条件对照**（同 prompt/同预算/同 target=GLM-5.3-Flash）：GLM / DeepSeek /
   更强 reasoning API，各生成 K=6，比较 disagreement、union repair、oracle headroom。
3. **只有当某条件 population 的 headroom ≥5pp 时**，才在该 population 上跑 LOHO 三层判据。
4. 样本量扩到 100-150 题（60 题下 headroom 判定噪声大）。

## 6. 对论文的影响

两个可报告的发现已经到手（无论最终主命题是什么）：
- **F1**：AI 生成的 harness population 可以在代码层面多样、行为层面塌缩（执行轨迹分级：
  纯 prompt 变体 / 无效反馈 / buggy 多轮）——这是"syntactic ≠ behavioral diversity"的
  首个系统测量（据我们所知）。
- **F2**：人工 diverse harness 在同一 target 上有 6.7pp headroom，证明 headroom 存在、
  瓶颈在生成侧。

若明天 stronger builder + 修复协议能把 AI 生成 population 的 headroom 拉起来，
则 "population diversity → routing headroom → value prediction" 的完整故事成立；
若拉不起来，"automatic harness generation fails to produce behavioral diversity" 本身
是论文的核心 finding。两条路都不需要现在决定 thesis 措辞。

## 7. 补充（对外部 review 的回应与增量，2026-08-31 晚）

### 7.1 进度映射

Review 的五步序列中，**Step 1（trace audit）与 Step 5（人工 positive control）已完成**
（本文件 §2、§3），Step 2-4（强 Builder 重生成 → 对照 → LOHO）是明天的主线。

### 7.2 对假设公式 f(builder, task signal, feedback, runtime freedom) 的具体化

四个变量我们都已有测量或证据，不是抽象概念：

- **builder capability**：待三条件对照检验（GLM-5.3-Flash / deepseek-chat / deepseek-v4-pro，
  后两者已用 cc-switch 现有 key 验证 OpenAI 兼容端点连通，零采购成本）；
- **task signal**：TTHE proposer 每轮只见 **3 道题**（cap=3），且 fitness 信号是 label-free
  proxy（metamorphic consistency / round-trip）——3 题上这些信号近似噪声，proposer 没有
  理由改变控制流。**信号饥饿是协议问题，不是 benchmark 问题**（positive control 已证
  benchmark 有 headroom）；
- **feedback**：proposer 读到的 trace 是 3 题的执行记录，含错误信息有限；
- **runtime freedom**：TTHE 有具体自由度限制——request_timeout 120s vs solve 墙 90s、
  retry ladder 无法在墙内完成（cand_b0r0_g0 的 docstring 精确记录了这一点）、frozen-solver
  audit 禁止新客户端、solver_cache 跨运行共享。

### 7.3 统计纪律

- 60 题上 1 题 = 1.67pp：positive control 的 6.67pp headroom ≈ 4 题，正式对照必须用
  **100-150 题**；
- 三 Builder 条件 × 多指标比较需预注册主指标与判定线，避免事后挑指标。

### 7.4 预注册判定线（写入冻结文档，明日执行）

对每个 Builder 条件（同 prompt、同预算、同 target=GLM-5.3-Flash、同 150 题）：

- 主指标：union repair rate（对 bare 错误）、oracle headroom（pp）、pairwise disagreement；
- **进 LOHO 的门槛：union repair ≥ 20% 且 oracle headroom ≥ 5pp**（positive control 已证
  人工可达成，AI 生成须追平）；
- 达标的最强 Builder 条件进入 LOHO 三层判据；全部不达标 → 论文主 finding 定为
  F1+F2（生成协议失败模式 + headroom 存在性），thesis 措辞届时再定。

### 7.5 前提条件清单作为贡献形状

"没有 harness behavioral diversity 就没有 value prediction 可学"可以操作化为三指标
检查表（disagreement / union repair / oracle headroom），作为论文的 precondition
section——后续任何 harness-routing 工作都应先过此检查表。这使今天的负结果与明天的
对照无论哪个方向都有论文形状。
