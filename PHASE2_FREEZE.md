# PHASE-II CONFIRMATORY PROTOCOL — FROZEN 2026-09-04

> Written and committed BEFORE any Phase-II confirmatory outcome was observed.
> This is a **pre-evaluation frozen internal decision rule**, not a formal external
> preregistration. Phase-I (everything before this file) is DISCOVERY. Nothing in Phase-I
> may be reported as confirmatory. Changes to this file after the first confirmatory run
> must be logged in §10 with a reason and are reported as deviations.

## 0. Why this document exists

Phase-I developed its hypotheses while looking at the same 151 items it reported on, and
24 of those items had been used for day-1 protocol development. Threshold values moved
(20% → 15%) during the study, and provenance rests on file mtimes rather than commits.
None of that can be undone retroactively. Phase-II therefore re-derives every headline
claim on data that no author, builder, or analysis script has ever read.

## 1. Contamination registry and splits

`experiment/phase2/touched_registry.py` scans every split file, outcome matrix and day-*
artifact for observed BIRD questions. Result: **313 of 1534 dev questions touched**, all
inside two databases.

Admissibility rule — stricter than item-level holdout: **a database is admissible only if
no question in it was ever observed.** Protocol development read `card_games` and
`formula_1` schemas, traces and outcomes, so both are banned wholesale, including the 52
`formula_1` items the registry marks individually untouched.

| Split | Content | N | Use |
|---|---|---|---|
| `split_p2_dev` | card_games + formula_1 | 365 | builder-visible; gate, prompt and threshold tuning |
| `split_p2_test` | the 9 never-opened databases | 1169 | **frozen confirmatory evaluation** |
| `split_p2_test_core` | stratified subsample of the above, seed 20260904 | 400 | wide sweeps with many harnesses |

`split_p2_test_core` was drawn **before any outcome existed**, so later use of it is not a
post-hoc selection. Database identity is retained on every item, which supplies the
leave-one-database-out grouping used in §7.

No builder prompt, harness, gate or analysis script may read `split_p2_test` items until
the confirmatory run. Harness code is hashed and frozen before that run and is not edited
afterwards.

## 2. Judge

**Primary: BIRD official execution accuracy.** `set(cur.fetchall()) == set(gold_fetchall())`,
30 s timeout, no row cap, any exception scores 0 — implemented in
`experiment/phase2/official_scorer.py` to match the official `evaluation.py`.

**Secondary: the legacy in-loop judge** (`ase.db.compare_results`, set of stringified
tuples under a 20000-row cap), reported for continuity with Phase-I.

Measured agreement on the two Phase-I matrices that logged `final_sql`:

| Matrix | cells | agreement | ours=1/official=0 | ours=0/official=1 | acc ours → official |
|---|---|---|---|---|---|
| eval151_round4 | 1963 | 0.9868 | **0** | 26 | 0.5099 → 0.5232 |
| eval151_qwentarget | 2718 | 0.9746 | **0** | 69 | 0.5324 → 0.5578 |

The legacy judge is **uniformly conservative**: it never credits an answer the official
scorer rejects. `tthe_eval151_matrix.parquet` predates `final_sql` logging and cannot be
re-judged offline; Phase-II records both judges natively on every cell.

## 3. Response caching — disclosed as a control, not an accident

Every harness shares a disk-backed cache of frozen-solver replies keyed on
`(prompt, system, temperature, n, seq)` (`ase/solver_cache.py`). `seq` counts how many
times *this harness instance* already issued *this exact* request, so deliberate
resampling still draws fresh samples while identical asks across harnesses collapse to one
reply.

This is load-bearing and must be stated in the paper. Its own measurement log records that
without the cache, byte-identical harnesses scored 6/10, 3/10 and 4/10 on the same
problems — a ±3 spread from pure sampling noise. **The cache therefore removes spurious
diversity.** Uncached measurement would *overstate* behavioural diversity, so caching makes
the collapse claim conservative rather than inflated.

Phase-II quantifies this instead of asserting it (§6, audit R2).

## 4. Frozen factors

**Builders** (six independent labs; frontier US models are not reachable from the
available endpoint, so the axis is builder *identity*, not builder *strength*):
GLM-5.3, Qwen3.8-Max, DeepSeek-V4-Pro, Kimi-K3, MiniMax-M3, ERNIE-5.0-Thinking-Preview.

**Targets** (frozen, temperature 0): GLM-5.3-Flash (primary), Qwen3.8-Flash (second),
DeepSeek-V4-Flash (third, capability contrast).

**Generation seeds**: 3 per (builder × protocol) cell.

**The 2×2**, which is the primary causal contrast:

| | no conformance gate | conformance gate |
|---|---|---|
| **free strategy** | A | B |
| **strategy-forced** | C | D |

*Strategy forcing* = the builder is assigned a named mechanism. *Free* = the builder is
asked to invent an improvement, with no mechanism named. *Conformance gate* = the harness
must pass `experiment/phase2/conformance.py` for its declared mechanism.

The gate judges the **execution trace against synthetic scenarios only**. It never reads
task performance, so it cannot leak outcome supervision into harness selection.

A fifth arm, **E (builder-discovered mechanism)**, separates human mechanism assignment
from AI discovery: the builder first emits a declarative mechanism spec, then implements
it, and is gated on its own declaration. This addresses the objection that the diversity
in arm D was injected by the authors' choice of six strategies.

## 5. Metrics

Reported as continuous effect sizes with paired bootstrap CIs (10,000 resamples over
tasks). The Phase-I admission thresholds (union repair ≥ 15%, oracle headroom ≥ 5 pp,
≥ 3 distinct fix sets) are retained **only** as a descriptive operational checklist and
are never used to label an arm a success or a failure.

1. **Pairwise outcome disagreement** — mean over harness pairs of the fraction of tasks whose correctness differs.
2. **Union repair rate** — `|{x : bare wrong, ∃H correct}| / |{x : bare wrong}|`.
3. **Union harm rate** — `|{x : bare right, ∃H wrong}| / |{x : bare right}|` (new; a population may repair a lot while breaking more).
4. **Oracle headroom** — oracle-any accuracy − best-fixed-harness accuracy.
5. **Effective behavioural population size** — `K_eff/K`, distinct outcome vectors over population size (new).
6. **Repair-set Jaccard matrix** — `|R_i ∩ R_j| / |R_i ∪ R_j|`, replacing the "≥3 distinct fix sets" count.
7. **Conformance profile** — share of the population at PASS / T1 / T2 / T3 / INVALID.

Primary contrasts are **differences between arms** with paired CIs, not each arm's CI
against a threshold.

## 6. Robustness audits

- **R1 Judge** — every cell dual-scored; all headline numbers reported under both.
- **R2 Cache** — the confirmatory matrix is replicated cache-off on `split_p2_test_core` for the A and D arms. Reports how much apparent disagreement is resampling artifact, and whether cache-off extra disagreement yields *stable* repair sets across repeats (it should not).
- **R3 Repeats** — 3 independent repeats of bare and of the D arm on `split_p2_test_core`, cache-off, giving an outcome flip rate and a repair-stability rate. Bootstrap CIs elsewhere cover task sampling only; this covers solver stochasticity.
- **R4 K-control** — population size held fixed across arms when comparing, so protocol effects are not size effects.
- **R5 Generation seeds** — 3 seeds per cell; arm metrics reported as mean ± SD across seeds.

## 7. Routing evaluation

Three generalization levels, each strictly harder:

- **L1 task-held-out** — unseen tasks, seen harnesses. Grouped by **database** (leave-one-database-out over the 9 test databases), never a random item hash, so a router cannot win by memorizing a schema.
- **L2 harness-held-out** — unseen harnesses, seen tasks (leave-one-harness-out).
- **L3 joint** — unseen tasks *and* unseen harnesses.

Baselines: R0 best-fixed harness; R1 task-only features; R2 task + harness mechanism
identity; R3 task + harness code/spec embedding; R4 a frontier LLM shown the task and the
harness spec, predicting `P(Δ=+1)/P(Δ=0)/P(Δ=−1)` without executing.

Because repair labels are sparse, **AUPRC and its prevalence baseline are reported
alongside AUROC**, plus policy gain over bare, regret to oracle, intervention rate, harm
rate, and a selective risk–coverage curve.

## 8. Second domain

LiveCodeBench, via the existing TTHE `livecodebench/` scaffold (no Docker; subprocess
execution; public sample tests as the label-free signal, hidden tests as gold). Scope is
deliberately limited to replication, not a second full paper: old protocol vs best
protocol, 2 builders, 1 target, plus a hand-written positive control.

## 9. What would falsify the paper's claims

- Collapse is a caching artifact → R2 shows cache-off disagreement is large *and* its extra repairs are reproducible across repeats.
- Collapse is judge-specific → official-judge disagreement/headroom differ materially from the legacy judge.
- The gate does nothing → arms C and D are indistinguishable, with the A→C difference carrying the whole effect.
- Mechanism diversity was purely author-injected → arm E collapses to arm A.
- The finding is BIRD-specific → LiveCodeBench shows no collapse under the old protocol.

Each is reported as measured, whichever way it comes out.

## 10. Changelog

- **2026-09-04 v1** — initial freeze. Registry (313/1534 touched), database-level splits, official judge wired and validated on two Phase-I matrices, conformance suite implemented and run over all 95 Phase-I harnesses (old protocol 0/40 PASS; strategy-forced 13/22 PASS; 4 GLM harnesses uncallable). Cache disclosed as a control. No Phase-II confirmatory outcome observed at time of writing.
- **2026-09-04 v1.1 — DISCLOSED DEVIATION.** The Phase-II collector's first pipeline smoke test was run against `split_p2_test` (2 items per database, 18 items) instead of `split_p2_dev`. Two aggregate accuracies were observed — `bare` 0.611 and `hpc_repair` 0.722 — over those 18 items. No per-item outcome was inspected, no trace was read, and no protocol, threshold, prompt or harness was changed as a result. The 18 items are **retained** in the confirmatory set: dropping them would make the test set depend on the smoke test, which is worse than disclosing it. All subsequent pipeline testing uses `split_p2_dev`.
- **2026-09-04 v1.2 — adversarial review (Codex, cross-model) and resulting corrections.** The reviewer scored the v1 protocol 2/10 / not-ready. Confirmed and fixed before any confirmatory run:
  - **Cache key omitted model identity.** `solver_llm` keyed on `(prompt, system, temperature, n, seq)` while Phase-II varies `SOLVER_MODEL` against one shared cache, so a Qwen target could be served a reply generated for GLM — silently erasing the entire target-transfer contrast. Model id and base_url are now part of the key.
  - **Collector shared one harness instance across worker threads.** `SQLHarness` carries mutable `_trace` and `_call_seq`; the latter is what makes deliberate resampling draw fresh samples. Now one instance per task.
  - **The official scorer had no real query timeout.** `sqlite3.connect(timeout=)` bounds lock waiting, not execution; a runaway generated query would hang a worker indefinitely. Now aborted via `set_progress_handler`; verified to interrupt an infinite recursive CTE at 30.0 s.
  - **The conformance gate was passable by a no-op.** The scripted majority answer was always first (so "return the first candidate" passed without voting) and the expected repair was always the second response (so "always call twice" passed without reading the error); answers were compared by substring containment. Replaced with **paired counterfactual variants** whose correct answer differs — including a variant where the first query *succeeds*, which is what separates conditional repair from an unconditional second call — and exact normalized equality.
  - **The gate produced false negatives on legitimate mechanisms.** With a stub database returning identical rows for every query, a harness voting by majority *execution result* (the objectively correct way to vote) was unfalsifiable and failed. Caught because the **hand-written positive controls failed**; they are now used as the gate's calibration set, and all three mechanism-bearing controls pass.
  - **`hint_guard` / `format_guard` are prompt-level by construction** and were being held to a control-flow contract they never claimed. Contracts are now declared per strategy, not inferred from filenames.
  - **"Old protocol: 0/40 conform, all T1" was categorically wrong.** All 40 `cand_oldds_*` / `cand_oldqwen_*` files are **byte-identical to `bare.py`** (verified by sha256). They did not implement a mechanism badly; generation produced nothing. New verdict `COPY_OF_BASELINE`. **This retracts the Phase-I claim that the 40-harness run shows builder-independent behavioural collapse** — with byte-identical code, "780/780 pairs identical, 0 repairs" is a tautology, not evidence. The paper's headline collapse claim is unaffected: it rests on the day-1 population, whose 14 harnesses were re-verified to have 14 distinct source hashes (14–135 lines) and which the corrected suite scores 12 PASS / 4 T1 / 3 T2 / 1 T3.

### Still open before the confirmatory run (from the same review)

1. **Registry is not fail-closed.** It scans split files, outcome parquets and `artifacts/day*/**/*.json` only — missing JSONL, logs, CSVs, caches and git history. Must be made recursive and fail-closed before it can be cited as a provenance statement.
2. **Arm E does not implement its stated control.** `accept()` ignores the emitted JSON spec and gates on the four-class `# MECHANISM` line, and `PROMPT_SPEC` still injects the author vocabulary — so E is neither self-gated nor vocabulary-free. Either rebuild it to compile the spec into independent trace assertions, or demote it to exploratory.
3. **Unequal generation budget across arms.** Gated arms retry up to 3 times while ungated arms accept the first importable candidate, confounding the gate with extra compute and rejection sampling. Fix to an equal proposal budget per builder/seed/arm and analyse intention-to-treat.
4. **No primary confirmatory hypothesis is named.** With 5 arms, 6 builders and 7 metrics there are many defensible post-hoc winners. One primary metric and one primary contrast must be fixed before the run; everything else is secondary.
5. **Task-level bootstrap is pseudo-replication** for a generation-level intervention. Pair builder×seed cells across arms and resample at that level, clustering tasks by database.
6. **The cache argument in §3 is too strong.** Caching is conservative only for the estimand "structural differences conditional on identical solver draws". Two harnesses that issue the same first request but diverge downstream would, uncached, receive independent draws and diverge further; the shared cache couples them and can therefore *create* apparent agreement. §3 must be restated and R2 must compare independent-randomness against common-random-number conditions.

