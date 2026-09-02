# §4 Measuring Behavioral Diversity: A Precondition Framework

*(draft v1, 2026-09-02; evidence: artifacts/day1/DIAGNOSIS.md, population_diagnosis.json, trace_audit.jsonl)*

## 4.1 Three metrics

If harness quality is conditional — $Q(H \mid x, M)$ rather than a scalar $Q(H)$ — then
a harness *population* is valuable only insofar as its members disagree on outcomes in
a structured, repair-bearing way. Code-level difference is cheap to obtain; outcome-level
difference is what routing consumes. We propose that any harness-generation pipeline
(or any harness-routing paper) report three precondition metrics on a held-out set:

1. **Pairwise outcome disagreement.** Over all harness pairs $(H_i, H_j)$, the fraction
   of tasks where $Y(x,H_i,M) \neq Y(x,H_j,M)$. Zero disagreement means the population
   is behaviorally one harness.
2. **Union repair rate.** The fraction of bare errors $x$ (where $\Delta(x,H_0,M)=-1$
   conceptually) such that *some* harness in the population answers correctly. This
   bounds what any selector over the population could achieve.
3. **Oracle headroom.** Accuracy of the per-item oracle selector
   $\max_i Y(x,H_i,M)$ minus the best fixed harness. Positive headroom means the
   population's value is *conditional on the item* — exactly the signal a value
   predictor or router would need.

These three metrics are cheap (they require only the outcome matrix
$Y \in \{0,1\}^{|X| \times |K|}$ that any evaluation already produces), hard to game
(they are defined on outcomes, not on code), and diagnostic in combination: high
disagreement with no union repair is noise; union repair with no headroom means one
harness dominates; headroom without disagreement is impossible by definition.

## 4.2 Trace audit: why code diversity fails to become behavioral diversity

Outcome metrics say *that* a population collapsed; they do not say *why*. We audit
execution traces — the sequence of LLM calls and artifact executions per task — and
find that "different code" decomposes into three failure classes:

- **T1 — Pure prompt variants (6/12 candidates).** The harness issues exactly one LLM
  call and never executes an artifact — the identical execution path as `bare`. The
  docstring may claim retrieval, self-checking, or token caps; none of it exists in
  the control flow. The mechanism is *described*, not *implemented*.
- **T2 — Feedback that cannot change the answer (react, 10/10 audited tasks).** The
  harness executes the SQL and feeds errors back to the model, yet its final SQL is
  byte-identical to `bare`'s on every audited task. Execution feedback exists in the
  loop but has no causal path to the output.
- **T3 — Buggy multi-turn paths (1/12).** The only candidate implementing genuine
  multi-turn repair returns prose as final SQL, converting bare-correct items into
  harness-wrong — the single negative-value behavior in the population.

This taxonomy turns "AI-generated harnesses are behaviorally collapsed" into an
actionable diagnosis: T1 demands an execution-path acceptance gate (§6), T2 demands
feedback mechanisms with a verified causal path, T3 demands executable-output
validation — all three are *generation-protocol* requirements, independent of the
benchmark.

## 4.3 The collapse, quantified

On the day-1 population (14 harnesses × 60 tasks, GLM-5.3-Flash target, TTHE proposer
protocol): average pairwise outcome disagreement **3.5%** (maximum 13.3%;
**28 of 78 pairs fully identical**), union repair over bare errors **7.7%** (2/26),
oracle headroom **3.3 pp** — and `react` differs from `bare` on **zero** tasks. Every
candidate passed a code-similarity check ("all files distinct, non-trivial diffs"):
the population is syntactically diverse and behaviorally one harness. To our
knowledge this is the first systematic measurement of the gap between syntactic and
behavioral diversity in AI-generated harness populations.

<!-- hero 图素材:左=代码 diff 热图(高亮多样性),右=outcome matrix(几乎一列);
     数据:artifacts/day1/population_diagnosis.json + tthe_bird_matrix.parquet -->
