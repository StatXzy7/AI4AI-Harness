# §5 Positive Control: The Headroom Exists

*(draft v1, 2026-09-02; evidence: artifacts/day1/DIAGNOSIS.md §3, positive_control_diagnosis.json.
数字为 60 题版;151 题复测到位后替换为 151 版。)*

Before attributing collapse to generation, we must exclude the alternative: that
BIRD/GLM simply has no exploitable instance-conditional signal — that *any* population,
however diverse, could only be noise. We therefore wrote four harnesses by hand, each
with an execution path forcibly different from bare:

- `hpc_repair` — execute the SQL; on error, feed the message back for one repair round;
- `hpc_vote3` — three independent samples at temperature > 0, majority vote on execution
  results;
- `hpc_schema` — a schema-linking pass that prunes the schema before generation;
- `hpc_hint` — re-order the question into hint-first form before generation.

Same frozen target, same 60 tasks, same judge as the collapsed AI population:

| Metric | AI population (A) | Human positive control |
|---|---|---|
| Pairwise disagreement | 3.5% | **8.6%** |
| Union repair of bare errors | 7.7% | **20.7%** |
| Oracle headroom vs best fixed | 3.3 pp | **6.67 pp** |
| Strategies with unique repairs | ≈ 0 | repair / schema / hint each contribute 3 |
| Union regressions | 7 | 4 |

Two conclusions. First, **F2**: the domain admits ≥ 5 pp of instance-conditional
headroom, so the routing-application premise survives. Second, the contrast localizes
the failure: identical target, identical task, identical judge — the only differing
variable is how the harness code came to exist. What the human harnesses share, and
the AI population lacks, is not better prompts but *different control flow*: extra
LLM calls, artifact executions, and aggregation steps that give the target model
genuinely different attempts. On the 151-item set the control's headroom holds at
**7.28 pp** [3.3, 10.0] while its repair rate settles at 14.9% — the 60-item 20.7% was
small-sample optimism, disclosed in §7 — so the two conclusions stand with tightened
numbers: **F2** (the domain admits ≥5 pp of instance-conditional headroom) and the
localization of the failure to the generation side.

# §6 Behavior-Aware Generation Protocols

*(draft v1, 2026-09-02 — 机制部分定稿,结果表 ⏳ 等 eval151 矩阵)*

The diagnosis of §4 suggests two orthogonal fixes. **Gated free-form** keeps the
builder fully expressive but adds an acceptance gate with teeth: the candidate is run
on probe questions and rejected unless its trace diverges from bare's (≥ 2 LLM calls
or ≥ 1 artifact execution, mechanically checked on the trace, not the docstring).
**Harness IR** removes free-form code generation altogether: mechanisms are declared as
a small typed IR (schema-pruning, multi-sample voting, execute-repair, hint
reordering, composition), and a deterministic compiler emits the harness
subclass. The IR arm thereby guarantees mechanism diversity by construction and
measures what each mechanism *does*, decoupled from builder coding ability.

We compare six populations under identical budget and target — old proposer protocol
(A), gated free-form with GLM (B) / Qwen (C) / DeepSeek (D), compiled IR, and the human
control — on 151 held-out questions. Admission to any downstream routing claim
requires the pre-registered thresholds of §3.4.

## 6.0 Results table (eval151, n=74 bare errors; CIs are task-level bootstrap 95%)

| Population | disagree | union repair [CI95] | headroom pp [CI95] | distinct fix sets | admitted? |
|---|---|---|---|---|---|
| A old-proposer (K=6) | 7.0% | 24.3% [.149,.347] | 4.64 [1.3,8.0] | 5 | no (headroom) |
| B GLM free-form | 0/6 generated | — | — | — | n/a |
| **C Qwen free-form (K=6)** | 11.1% | 21.6% [.125,.310] | **5.96** [2.0,8.6] | 6 | **yes** |
| **D DeepSeek free-form (K=6)** | 11.2% | 24.3% [.148,.346] | **7.95** [4.0,11.3] | 6 | **yes** |
| IR compiled (K=6) | 8.2% | 16.2% [.083,.253] | 3.97 [1.3,7.3] | 6 | no (headroom) |
| Human control (K=4) | 8.9% | 14.9% [.071,.237] | 7.28 [3.3,10.0] | 4 | no (repair, by 0.1pp) |
| Cross-protocol pool (K=24) | 10.3% | 37.8% [.268,.488] | **11.26** [6.6,15.9] | 23 | yes (analysis) |

Three observations. **(i) Behavior-aware generation closes the diversity gap.** Both
free-form populations built by stronger builders clear all three pre-registered
thresholds — the first AI-generated populations to do so — with disagreement more than
3× the day-1 level and six pairwise-distinct repair sets apiece. **(ii) The trend
follows the builder-and-protocol axes.** The old proposer protocol produces a population
whose best member dominates (0.583, the single highest harness in the study), squeezing
headroom to 4.64 pp despite a healthy repair rate — diversity without *spread*. The
weakest builder cannot pass the generation gate at all (0/6). Capability and protocol
are jointly necessary: neither alone suffices. **(iii) The human control is not a
universal upper bound.** Its 60-item repair rate (20.7%) shrank to 14.9% on 151 items —
small-sample optimism we had flagged in advance — while its headroom (7.28 pp) stayed
strong: hand-designed harnesses are complementary specialists, not uniformly stronger
solvers. We report the borderline cases (IR at 3.97 pp, human at 14.9%) exactly as
measured, without post-hoc threshold adjustment.

## 6.1 Does diversity buy learnable routing? (honest negative)

For the two admitted populations we ran the pre-registered leave-one-harness-out
value-prediction protocol (logistic heads on task text + harness features; threshold
tuned on a disjoint item half). It does **not** beat the best fixed harness: D6 −3.4 pp,
C6 +0.9 pp (bootstrap CI spans zero), cross-protocol pool −0.9 pp. Unseen-harness
representation adds ≤0.001 AUROC over task-only features — the open-set signal that
Day-0 found absent at the configuration level is still absent at the level of admitted,
executable populations. Two honest positives temper the negative: the same predictor,
used as a *gate* over the 24-harness pool, gains **+6.9 pp** over the bare baseline
while incurring **zero harness-induced harm** on its interventions (it abstains rather
than routes into damage), and the closed-set router (harness identity visible) shows
weak but nonzero signal (AUROC 0.575). Diversity, in other words, is *necessary* for
routing value to exist — without §6 it is provably absent — but it is not
*sufficient*: estimating an unseen harness's per-item value from code and task text
alone remains open.
