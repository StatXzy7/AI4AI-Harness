# PHASE-II STATISTICAL ANALYSIS PLAN — FROZEN 2026-09-04

> Companion to `PHASE2_FREEZE.md` (splits, judge, caching, contamination registry).
> This document fixes the **estimands, the generation budget, and the inference procedure**
> before any confirmatory outcome is observed. Deviations are logged in §9.
>
> Status at time of freezing: no Phase-II harness has been evaluated on `split_p2_test`
> except the 18-item pipeline smoke disclosed in `PHASE2_FREEZE.md` §10 v1.1.

## 1. Arms

Two crossed factors. *Strategy forcing* S: the builder is assigned a named mechanism (S=1)
or asked to invent one with no mechanism prescribed (S=0). *Conformance gate* G: the harness
must pass the frozen conformance suite (G=1) or only neutral validity (G=0).

| | G=0 ungated | G=1 gated |
|---|---|---|
| **S=0 free** | **A** | **B** |
| **S=1 forced** | **C** | **D** |

**Arm E — open mechanism discovery.** The builder receives *no mechanism vocabulary at all*:
no repair, voting, schema-linking, critique or decomposition. It is gated on whether its
implementation honours **its own** declared contract.

E is a **pre-specified secondary arm and is deliberately not a fifth factorial cell.** It
answers a different question — whether builders can autonomously discover, faithfully
implement, and *accurately describe* behaviourally distinct mechanisms without author-supplied
strategy labels — and must not contaminate the A–D causal design.

### E is elicited in two stages

A single call asking for code *and* a contract requires the builder to predict its own
behaviour before writing it, which is both unfair and confounded. Instead:

- **E1 — free generation.** No mechanism vocabulary, and the contract DSL is withheld, so the
  implementation cannot be steered by the language it will later be audited in. The emitted code
  is written to disk and **frozen**.
- **E2 — self-audit.** The same builder is shown its own frozen implementation and the generic
  trace DSL, and asked for the **minimal** set of assertions the code actually guarantees:
  *omit anything you cannot establish; an omitted assertion costs nothing, a false assertion
  causes rejection.* E1 is never regenerated in response to E2, and the gate never edits the
  contract it is handed.

This separates three abilities that a one-shot protocol conflates: discovering a mechanism,
implementing it, and describing it accurately.

### The contract DSL (the entire vocabulary arm E receives)

`min_llm_calls`, `min_executions`, `min_distinct_samples`, `branches_on_execution`,
`carries_data_forward`, `final_from_last_generation`, `final_invariant_to_sample_order`.

These are instrumentation primitives — an LLM call, an execution, an ordering, a data
dependency, a branch, a permutation invariance — not mechanism names. Some such ontology is
unavoidable for any trace-based verification; what is avoided is naming the mechanisms.

Contracts are **sparse**: an unasserted property is neither false nor a failure. Only asserted
properties are checked.

### Three-layer gate

1. **Contract validity** — well-formed, keys drawn only from the DSL, at least one assertion.
2. **Non-vacuity** — the contract must be violated by `bare.py`, enforced by literally running it.
   This is a **generic trace difference**, `C(H) ≠ C(H₀)`; it does *not* require conditional
   branching, since a multi-sample mechanism can be non-vacuous through `min_distinct_samples`
   alone.
3. **Conformance** — every **asserted** property is verified. Conditional and content-based
   assertions trigger paired counterfactual probes: `branches_on_execution` is tested against a
   probe pair differing only in whether the first query executes cleanly, so an unconditional
   second call cannot impersonate conditional repair; `final_invariant_to_sample_order` is tested
   against a permutation of one sample multiset plus a changed multiset, so returning a fixed
   position cannot impersonate selection.

Admission is `neutral-valid ∧ contract-valid ∧ non-vacuous ∧ all asserted claims conform`.

**Failed properties are never dropped automatically.** Narrowing a contract to the subset a
harness happens to satisfy would let the evaluator repair the builder's declaration after
reading the trace, which is relabelling a mechanism after seeing how it behaved.

### Arm E reports three rates, not one admission number

    R_artifact   neutral-valid code (parses, imports, returns SQL)
    R_contract   contract valid and non-vacuous
    R_fidelity   all asserted properties verified, CONDITIONAL on a valid contract

"artifact validity 95%, mechanism present 80%, self-contract fidelity 25%" is a research
finding; "E admitted 2/8" is not.

## 2. Equal raw generation budget

Every slot in every arm receives exactly **R = 3** raw builder attempts, with identical model,
temperature (0.7), token cap (16384) and prompt scaffold. Arms differ **only** in which raw
candidate is admitted:

- **ungated (A, C)** — first candidate passing **neutral validity**: parses, imports against both
  dev databases, exposes the required interface, and returns non-empty SQL on a dev question.
  Neutral validity is mechanism-blind by construction.
- **gated (B, D, E)** — first candidate passing neutral validity **and** the frozen gate.

Without this, gated arms would receive three generation opportunities against the ungated arms'
one, and any gain would be confounded with rejection sampling and extra compute.

**Slot failure is final.** If no raw candidate is admitted, the slot stays empty and K is
smaller. Generation is never topped up to reach K, which would reintroduce the asymmetry.

All raw candidates are retained. Generation *reliability* — `P(neutral valid)` and
`P(mechanism pass)` per raw attempt — is reported separately from the *quality* of the admitted
population, so "the builder cannot write it" is never confused with "what it wrote has no value."

## 3. Primary estimand

**Primary metric: oracle headroom** on the frozen confirmatory set, under the **official BIRD**
execution judge:

    H(P) = Acc(oracle-any over P) − max_{H ∈ P} Acc(H)

Union repair is *not* the primary metric. A population can repair many bare errors while
delivering no routing-relevant complementarity: if one member repairs 30% of bare errors and is
also the best fixed harness, union repair is 30% but headroom is ≈ 0. Headroom is what the
paper's thesis — that generated populations must exhibit instance-conditional complementarity
before routing is meaningful — actually asserts.

**Primary contrast: D − A**, paired by (builder × generation seed).

> **Primary hypothesis.** On the frozen untouched BIRD confirmatory set, the strategy-forced,
> behaviourally gated generation protocol (D) produces harness populations with greater oracle
> headroom over the best fixed harness than unconstrained, ungated generation (A), under the
> official BIRD execution judge. The primary estimand is the paired D−A difference in oracle
> headroom, paired by builder and generation seed.

    H₀ : H(D) − H(A) ≤ 0        H₁ : H(D) − H(A) > 0

Reported as a point estimate with a **two-sided 95% CI** and a paired permutation p-value.
A one-sided hypothesis is registered; a one-sided p-value alone is not reported.

## 4. Confirmatory secondary contrasts

Fixed now, in this order, tested only after the primary:

1. **Gate main effect** — `[(B−A) + (D−C)] / 2`
2. **Strategy main effect** — `[(C−A) + (D−B)] / 2`
3. **Strategy × gate interaction** — `(D−C) − (B−A)`

The interaction is the most important *mechanism* result. A large positive interaction supports
"strategy differentiation alone is insufficient; execution fidelity is required to realize it."
Main effects can mask exactly this, which is why neither is primary: if free builders already
produce conformant harnesses, `B−A` may be ≈ 0 while `D−C` is large.

Holm correction across these three. Everything below is secondary/exploratory and reported with
simultaneous bootstrap intervals, never as significance claims.

## 5. Secondary outcomes

Key secondaries, in order: **union repair rate**; **pairwise outcome disagreement**; **union harm
rate**; **effective population size** `K_eff/K` (distinct outcome vectors, reported as "unique
outcome-vector fraction" — it measures exact duplication, not effective rank); **repair-set
Jaccard matrix**. Then: builder differences, target transfer, conformance profile, arm E.

### Mechanism diversity (descriptive; no directional hypothesis registered)

`K_mech(P)` — the number of distinct mechanism signatures in a population. For arms A/B the
signature is the builder's `# MECHANISM` declaration; for arm E it is the tuple of boolean
contract keys it asserted; for arms C/D it is the assigned strategy (so `K_mech = K` by
construction, and the measure is informative only for A, B and E).

This measure is registered **now, before any confirmatory outcome**, purely so that reporting it
later is not post-hoc. **No directional hypothesis is attached to it.** It is motivated by an
observation on *dev-side generation only* — that a strong builder given no mechanism vocabulary
emitted contracts that all asserted `branches_on_execution` and `carries_data_forward` — but
whether that reflects a real convergence, and whether it relates to headroom, is left entirely
to the confirmatory data. It is reported whichever way it comes out, and it will not be promoted
to a headline claim on the basis of the dev-side observation that motivated measuring it.

## 6. Inference

The confirmatory set is 9 databases × ~130 questions. Items within a database share a schema and
are plainly correlated, and the intervention is applied to builder×seed populations rather than
to tasks — so a naive i.i.d. task bootstrap is pseudo-replication in one direction and ignores
clustering in the other.

**Hierarchical paired bootstrap.** For each replicate: resample the 9 databases with replacement,
then resample tasks with replacement within each drawn database; simultaneously resample
(builder × seed) cells with replacement, keeping arms **paired** within a cell. 10,000
replicates. This respects both blocking factors without a parametric model.

**Permutation test** for the primary: within each (builder × seed) cell, randomly swap the A and
D labels; recompute D−A; 10,000 permutations.

Task-level-only bootstrap intervals may be reported alongside, explicitly labelled as
*conditional on the realized harness populations*.

## 7. K-matching

Oracle headroom increases mechanically with population size K, and slot failures make K differ
across arms. The primary contrast is therefore reported twice:

- at **nominal K** (whatever each arm admitted), and
- at **matched K**, subsampling every population down to the minimum common K across the arms
  being compared, averaged over 200 random subsets.

A **K-sensitivity curve** `H_D(K) − H_A(K)` for K = 2 … K_min is reported. Stability across K is
what rules out a population-size artifact.

## 8. Exclusion rules and instrument freeze

- **Gate freeze.** The conformance suite and contract verifier are frozen as of commit
  `683e033` + the contract module. They were calibrated *before* any Phase-II outcome, against
  known-good human implementations (`hpc_repair`, `hpc_vote3`, `hpc_schema` — all must pass) and
  known-negative mutants (`neg_uncond_twocall`, `neg_selectfirst` — both must fail). **They are
  not modified in response to how Phase-II candidates score.**
- **Exclusions.** A harness is excluded only if it is uncallable (`INVALID_uncallable`) or
  byte-identical to the baseline (`COPY_OF_BASELINE`). No outcome-based exclusion exists.
- **Frozen after generation.** Harness source is hashed at admission and never edited.
- **Targets.** GLM-5.3-Flash (primary), Qwen3.8-Flash (second), DeepSeek-V4-Flash (third).

## 9. Revised failure taxonomy

Phase-I collapsed several qualitatively different failures into one. They are now separated
into a ladder, where each rung requires everything below it to have succeeded:

- **M0 — generation null.** No distinct artifact: `SHA256(H_i) = SHA256(H₀)`. All 40
  old-protocol `cand_oldds_*`/`cand_oldqwen_*` harnesses are M0. **The Phase-I claim that this
  run demonstrates builder-independent behavioural collapse is retracted**: with byte-identical
  code, "780/780 pairs identical, 0 repairs" is a tautology. The data are kept, reported as M0.
- **M1 — mechanism absent.** Distinct code, but the described mechanism never executes
  (Phase-I *T1*).
- **M2 — mechanism present, causal effect absent.** It executes and observes feedback, but
  nothing downstream depends on it (Phase-I *T2*).
- **M3 — mechanism present but broken.** A real multi-step path with a faulty implementation
  (Phase-I *T3*).
- **M4 — mechanism present, self-specification unfaithful.** The mechanism is genuinely
  implemented and non-vacuous, but the builder's own description of its behaviour asserts
  properties the implementation does not have.

M4 is new, and was surfaced by the arm-E calibration pilot (§10). It matters because it is the
same thesis one level up: **LLM-generated artifacts can look richer in their descriptions than
they are in their behaviour.** Whether M4 replicates across builders and seeds is left to the
confirmatory data; no directional hypothesis is registered for it.

The headline collapse claim concerns **M1–M3 within genuinely distinct artifacts**, and rests
on the day-1 population: 14 harnesses, 14 distinct source hashes, 14–135 lines, scored 12 PASS /
4 M1 / 3 M2 / 1 M3 by the corrected suite.

## 10. Changelog

- **2026-09-04 v1** — initial freeze. Primary estimand (oracle headroom, D−A, paired by
  builder×seed, official judge), confirmatory secondary hierarchy, equal raw generation budget
  R=3, slot-failure and K-matching rules, hierarchical paired bootstrap, gate freeze with
  positive- and negative-control calibration, taxonomy revision. No confirmatory outcome
  observed at time of writing.
- **2026-09-04 v1.1 — arm E contract-elicitation protocol replaced; A–D untouched.**
  The first arm-E protocol asked for code and contract in one call and admitted 0 of 4 slots
  (`R_artifact` 0.92, mechanism pass 0.00). Diagnosis showed this was **neither a gate failure
  nor an implementation failure**: the implementations were real and non-vacuous, and the
  builder systematically **over-asserted** its own contract — one candidate declared all seven
  DSL properties, including `branches_on_execution`, while making four LLM calls and returning
  the same answer whether or not the first query executed cleanly.

  To confirm the gate was discriminating rather than merely strict, one contract was **manually**
  reduced to the five properties the implementation satisfies; it then passed, and the reduced
  contract was still non-vacuous. **That reduction was a gate-calibration measurement only.** It
  is not an admission decision, no automatic property-dropping exists, and the candidate is not
  admitted — letting the evaluator narrow a contract after reading the trace would be relabelling
  a mechanism after observing its behaviour.

  Consequently: the four pilot candidates and the three pre-freeze smoke runs are quarantined in
  `artifacts/phase2/calibration_pilot/` and **excluded from every quantitative table**; arm E is
  regenerated from seed 0 under two-stage elicitation with the three-layer gate; and the pilot's
  finding is recorded as the new taxonomy rung **M4**. This change is based on measurement
  calibration, not on any confirmatory outcome.

  **A–D are unaffected.** Their admission rule (`neutral-valid ∧ (mechanism-pass ∨ ungated)`) and
  the conformance semantics they use are byte-identical to the frozen version; the arm-E work is
  confined to an `arm == "E"` branch and an E-specific prompt pair. A–D generation ran, and
  continues to run, under gate commit `a87ced4`.
