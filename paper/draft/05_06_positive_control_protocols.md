# §5 Positive Control: The Headroom Exists

*(draft v2, 2026-09-03; evidence: artifacts/day1/DIAGNOSIS.md §3, positive_control_diagnosis.json,
hpc_fixset_audit.json. 60 题为初步估计,以 151 题复测为准;bare 跨运行差异已披露。)*

Before attributing collapse to generation, we must exclude the alternative: that
BIRD/GLM simply has no exploitable instance-conditional signal — that *any* population,
however diverse, could only be noise. We therefore wrote four harnesses by hand, each
with an execution path forcibly different from bare:

- `hpc_repair` — execute the SQL; on error, feed the message back for one repair round;
- `hpc_vote3` — three independent samples at temperature > 0, majority vote on execution
  results;
- `hpc_schema` — a schema-linking pass that prunes the schema before generation;
- `hpc_hint` — re-order the question into hint-first form before generation.

Same frozen target, same 60 tasks, same judge as the collapsed AI population. One
caveat is auditable in the released matrices: the bare baseline itself flipped 3 of
60 items between the two day-1 runs (26 vs. 29 bare errors; API nondeterminism at
temperature 0), so the two columns are not conditioned on an identical bare-error
set. On the 60-item run:

| Metric | AI population (A) | Human positive control |
|---|---|---|
| Pairwise disagreement | 3.5% | **8.6%** |
| Union repair of bare errors | 7.7% (2/26) | **20.7%** (6/29) |
| Oracle headroom vs best fixed | 3.3 pp | **6.67 pp** |
| Harnesses with distinct non-empty fix sets | 1 | **3** (repair {36,38,53}, schema {11,12,38}, hint {38,43,53}) |
| Union regressions | 7 | 4 |

The fix-set audit (`hpc_fixset_audit.json`) makes the complementarity claim precise
and replaces our earlier, stronger phrasing: repair/schema/hint each produce repairs
the others miss (1/2/1 repairs unique to one harness), their fix sets are pairwise
distinct, and `vote3` contributes no repair on this run. On the 151-item set the
control's headroom holds at **7.28 pp** [3.3, 10.0] while its repair rate settles at
14.9% — the 60-item 20.7% was small-sample optimism, disclosed in §7 — so the two
conclusions stand with tightened numbers: **F2** (the domain admits ≥5 pp of
instance-conditional headroom at the point estimate) and the localization of the
failure to the generation side.

# §6 Behavior-Aware Generation Protocols

*(draft v3, 2026-09-03 — round-1 审后修订:协议细节、口径与 CI 已按审稿意见收紧)*

The diagnosis of §4 suggests two orthogonal fixes. **Strategy-forced free-form** keeps
the builder fully expressive but forces an explicit mechanism per candidate;
**Harness IR** removes free-form code generation altogether. This subsection specifies both at the level
needed for replication; prompts, specs, and compiled harnesses are released verbatim.

**Gated free-form protocol.** For each of six mechanism strategies $s$ (execute-repair,
3-vote, schema-linking, hint-guard, decomposition, format-guard), the builder receives
a fixed prompt: the `SQLHarness` interface (constructor-provided schema; `self.llm`
and `self.execute` primitives; `bridge.extract_sql`), the strategy description (one
sentence, e.g. *"Generate SQL, then EXECUTE it via self.execute(); if execution fails,
feed the exact SQLite error back and regenerate up to 2 times"*), and the required
class name. The builder emits one complete Python file per strategy (temperature 0.7);
the candidate is extracted from its code fence and written to the population directory.
For the two 09-01 populations (conditions C and D) acceptance was: file written and
hash-registered, with import and smoke checks performed at evaluation time; per-attempt
generation logs were not retained — a provenance gap we disclose, and which the day-3
generation tool (`builder_generate3.py`) closes for all runs after 2026-09-03 by
logging every attempt (3 retries, 16 384-token budget) and accepting a candidate only
after it imports against both databases and solves one builder-visible question. The
condition-B registry records zero accepted outputs from six strategies; because that
run predates the logging tool, we report condition B as a single unaudited observation
rather than a capability attribution, and we are re-running it under the logging tool. Builders see $D_{\mathrm{build}}$ only; no evaluation item or
outcome is shown to any builder. Budget: one generation call per strategy per run
(16 384 max tokens); failed extractions are not retried within a run — a design
choice that keeps per-strategy acceptance an auditable, single-shot reliability
observation (condition B's original unaudited run is superseded by the logged
re-run, §6.0).

**Harness IR.** Mechanisms are declared as a typed spec —
`context ∈ {plain, schema_link, hint_guard, link+hint}`, `generate.candidates ≥ 1`
with temperature, `execution.execute_each ∈ {0,1}`, `repair.on_error` with
`max_rounds`, `selection ∈ {first_ok, majority_rows, llm_judge}` — and a deterministic
compiler emits the harness subclass from fixed code templates. The builder (or human)
chooses and parameterizes modules; it cannot emit control flow, so a declared
mechanism is present in the control flow *by construction*. The six IR harnesses
enumerate the spec grid (plain/repair/vote3/hint-repair/schema-repair/link+vote3).

We compare six populations under identical budget and target — old proposer protocol
(A), strategy-forced free-form with GLM (B) / Qwen (C) / DeepSeek (D), compiled IR, and the
human control — on the builder-held-out 151-question set. Admission to any downstream
routing claim requires the pre-registered thresholds of §3.4.

## 6.0 Results table (eval151, n=74 bare errors; CIs are task-level bootstrap 95%)

| Population | disagree | union repair [CI95] | headroom pp [CI95] | distinct fix sets | admitted? |
|---|---|---|---|---|---|
| A old-proposer (K=6) | 7.0% | 24.3% [.149,.347] | 4.64 [1.3,8.0] | 5 | no (headroom) |
| B GLM free-form (logged re-run, K=3) | 3/8 strategies accepted | see §6.0b | see §6.0b | 3 | see text |
| **C Qwen free-form (K=6)** | 11.1% | 21.6% [.125,.310] | **5.96** [2.0,8.6] | 6 | **yes** |
| **D DeepSeek free-form (K=6)** | 11.2% | 24.3% [.148,.346] | **7.95** [4.0,11.3] | 6 | **yes** |
| IR compiled (K=6) | 8.2% | 16.2% [.083,.253] | 3.97 [1.3,7.3] | 6 | no (headroom) |
| Human control (K=4) | 8.9% | 14.9% [.071,.237] | 7.28 [3.3,10.0] | 4 | no (repair, by 0.1pp) |
| Cross-protocol pool (K=24) | 10.3% | 37.8% [.268,.488] | **11.26** [6.6,15.9] | 23 | yes (analysis) |
| B3 GLM logged re-run (K=3) | 8.8% | 21.6% | 5.96 | 3 | yes (post-hoc, K=3) |
| C8 Qwen completed grid (K=7) | 10.4% | 21.6% | 5.96 | 7 | yes (post-hoc) |
| D8 DeepSeek completed grid (K=8) | 10.6% | 28.4% | **9.93** | 8 | yes (post-hoc) |

*Rows 7–9 are the post-hoc completed-grid analysis (§6.2): the original admission decisions (rows 1–6) are unchanged; the GLM re-run population clears the checklist at K=3, though its small size limits any downstream claim.*

Three observations. **(i) Behavior-aware generation restores behavioral diversity.**
Both free-form populations built by Qwen and DeepSeek exceed all three pre-registered
thresholds *at the point estimate* — the first AI-generated populations to do so —
with disagreement more than 3× the day-1 level and six pairwise-distinct repair sets
apiece. We note for calibration that the headroom intervals [2.0, 8.6] and [4.0, 11.3]
include sub-threshold values; admission follows the frozen point-estimate rule, and
the intervals are reported so readers can apply a stricter reading. **(ii) The
contrasts localize the failure modes.** Within the old proposer protocol, the best
member dominates (0.583, the single highest harness in the study), squeezing headroom
to 4.64 pp despite a healthy repair rate — diversity without *spread*; this population
misses the headroom threshold by 0.36 pp rather than collapsing outright (the outright
collapse is the day-1 finding of §4). Under the logged generation tool, per-strategy acceptance orders with builder
capability — GLM 3/8, Qwen 7/8 (its vote3 attempts end with well-formed prose but no
code fence), DeepSeek 8/8 — replacing the unaudited original 0/6 observation (§6
discloses the provenance gap). Protocol
and builder are jointly implicated by these two contrasts, though the design cannot
separate their main effects (§3.4). **(iii) The human control is not a universal
upper bound.** Its 60-item repair rate (20.7%) shrank to 14.9% on 151 items —
small-sample optimism we had flagged in advance — while its headroom (7.28 pp) stayed
strong: hand-designed harnesses are complementary specialists, not uniformly stronger
solvers. We report the borderline cases (IR at 3.97 pp, human at 14.9%) exactly as
measured, without post-hoc threshold adjustment.

## 6.2 Completed-grid re-analysis (post-hoc)

After the pre-registered comparison, we completed the strategy grid: DeepSeek gained
schema-link and hint-guard (its weakest strategies are none; it accepts 8/8), Qwen
gained execute-repair (its vote3 attempts consistently emit prose without a code
fence and are logged; 7/8), and GLM was re-run under the logging tool (3/8). On the
completed grids, every builder's population clears the checklist: B3 (the three
harnesses GLM produced) reaches 5.96 pp headroom and 21.6% union repair with three
distinct fix sets; C8 holds at 5.96 pp / 21.6% with seven; D8 rises to **9.93 pp /
28.4%** with all eight strategies contributing a distinct fix set. Per-strategy
accuracies show no builder dominance (Qwen wins hint-guard 0.556 vs 0.510; DeepSeek
wins repair 0.543 vs 0.550 for Qwen; GLM's vote3 reaches 0.543) — capability orders
*generation reliability*, not per-strategy solution quality. These rows are labeled
post-hoc: the frozen admission decisions belong to rows 1–6.

## 6.1 Does diversity buy learnable routing? (honest negative)

For the two admitted populations we ran the pre-registered leave-one-harness-out
value-prediction protocol: logistic heads on task TF-IDF text plus harness code and
structural features, one held-out harness per fold, with a hash-based item split
(20% tune / 80% eval) used only for threshold selection. It does **not** beat the best
fixed harness: D6 −3.4 pp, C6 +0.9 pp (bootstrap CI [−5.2, +6.9]), cross-protocol pool
−0.9 pp (CI [−6.0, +4.3]); full per-fold results are in the released JSONs. Two
caveats sharpen — rather than soften — this negative. First, LOHO holds the task set
fixed, so the high per-fold AUROC on repair (0.82–0.98) largely reflects *task
memorization*: in a task-held-out control on D6 (train on 76 tasks, test on the 75
unseen tasks; `task_split_D6.json`), the repair classifier falls to chance (AUROC
0.475) and the policy degrades to the bare baseline. This is a single-population
control, not a sweep; but it removes the main alternative reading of the LOHO AUROC,
and task-side generalization of harness value fails where tested. Second, the pre-registered
three-level gate returns: L1 (headroom) **passes**; L2 (closed-set, harness identity
visible) **marginally fails** — its pre-registered criterion was a policy gain of
≥2 pp, which no closed-set configuration demonstrates; the closed-set repair AUROC
is 0.471 on D6 and 0.575 on the 24-harness pool, at chance to barely above chance); L3 (open-set, unseen harness) **fails** with unseen-
harness representation adding ≤0.001 AUROC over task-only features. One deployment-
relevant positive survives, and we state its scope precisely: on the 24-harness
cross-protocol pool only, the same predictor used as an *abstaining gate* gains
**+6.9 pp** over bare with zero harness-induced harm on its interventions (the
admitted single-builder populations show intervention harm of 2.8% and 8.7%). The
open problem stands: estimating an unseen harness's per-item value from code and task
text alone, on tasks the predictor has not seen, is unsolved by our strongest attempt.
