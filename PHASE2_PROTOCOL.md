# PHASE-II PROTOCOL — AUTHORITATIVE MERGED VERSION

> This is the single authoritative protocol document. It supersedes, in full:
> `PHASE2_FREEZE.md` (v1.0–v1.2), `PHASE2_SAP.md` (v1.0–v1.5), and
> `experiment/phase2/SAP_v2.md`. Those files are retained as tombstones pointing here.
>
> **Freeze anchor:** the commit SHA in `PROTOCOL_FREEZE.txt` (created immediately after the
> commit containing this document). Any post-freeze change requires a changelog entry here
> with a reason, and re-anchoring.
>
> **Confirmation of pre-outcome state:** at the time of this merge no `split_p2_test`
> evaluation has been run and no confirmatory outcome has been read. The only Phase-II
> outcomes ever observed are the 18-item pipeline smoke test disclosed in §10 (deviation D1)
> and generation-side (dev-side) artifacts, which involve no test-set outcomes.

**Real date of this document:** 2026-09-04.

---

## 1. Study structure

**Phase-I (completed, DISCOVERY ONLY):** all pre-Phase-II results, including the 151-item
pilot (24 of whose items participated in protocol development), the human positive control
(designed after reading dev-set traces), and the old-protocol populations. Phase-I results may
motivate hypotheses; they are never reported as confirmatory evidence.

**Phase-II (confirmatory):** everything defined below. Evaluation on `split_p2_test` happens
once, after generation completes and this protocol is frozen.

## 2. Contamination registry and splits

`experiment/phase2/touched_registry.py` scans the repository for observed BIRD questions.
It is **fail-closed**: files it cannot read are listed in `unscanned`; a non-empty list means
the registry is incomplete and must not be cited. Scope limits (stated, not hidden): git
history is not walked; filesystem scanning cannot establish human or pretraining exposure.
The defensible claim is "no project-specific adaptive use", not "never seen".

Admissibility rule — stricter than item-level holdout: **a database is admissible only if no
question in it was ever observed.** `card_games` and `formula_1` are banned wholesale.

| Split | Content | N | Use |
|---|---|---|---|
| `split_p2_dev` | card_games + formula_1 | 365 | builder-visible; gate/prompt/threshold tuning |
| `split_p2_test` | 9 never-opened databases | 1169 | **frozen confirmatory evaluation** |
| `split_p2_test_core` | stratified subsample, seed 20260904, drawn pre-outcome | 400 | factorial secondaries (all four arms on identical items) |

Registry outcome: 313/1534 questions touched (all inside the two banned databases); 18 further
test items disclosed as deviation D1. Untouched pool: 1203.

## 3. Judge

**Primary: BIRD official execution accuracy** — `set(fetchall())` equality, 30 s wall-clock
timeout enforced via `set_progress_handler` (verified to abort an infinite recursive CTE at
30.0 s), no row cap, exceptions score 0.

**Secondary: the legacy in-loop judge** (set of stringified tuples, 20000-row cap), reported
for continuity. Measured agreement on the two Phase-I matrices that logged `final_sql`:
0.9868 and 0.9746, with `ours=1/official=0` equal to **zero** in both — the legacy judge is
uniformly conservative. Phase-II records both judges natively on every cell.

## 4. Response caching — disclosed control

Every harness shares a disk-backed cache keyed on
`(model, base_url, prompt, system, temperature, n, seq)`. **Model identity and endpoint are
part of the key** (fix D7). `seq` preserves deliberate resampling. The cache removes spurious
diversity (its own log: without it, byte-identical harnesses scored 6/10, 3/10, 4/10 on the
same problems), so cached measurement is conservative for structural disagreement. The R2
audit quantifies this rather than asserting it: cache-off replication of arms A and D on
`split_p2_test_core`, comparing independent-randomness against common-random-number
conditions.

## 5. Arms and generation

Two crossed factors: strategy forcing **S** (assigned mechanism vs invent-your-own) and
conformance gate **G** (frozen conformance suite vs neutral validity only).

| | G=0 ungated | G=1 gated |
|---|---|---|
| **S=0 free** | A | B |
| **S=1 forced** | C | D |

**Arm E — open mechanism discovery** (pre-specified SECONDARY arm, not a fifth factorial
cell). Two-stage elicitation: E1 free generation with the contract DSL withheld, code frozen
to disk; E2 the same builder audits its own frozen code in the generic trace DSL and emits the
**minimal** assertion set (omission is free, a false assertion rejects). No mechanism
vocabulary is supplied anywhere in E.

**Equal raw generation budget.** Every slot in every arm receives exactly R=3 raw builder
attempts (identical model, temperature 0.7, token cap 16384). Arms differ only in which raw
candidate is admitted:

- ungated (A, C): first candidate passing **neutral validity** — parses, imports against both
  dev databases, correct interface, non-empty SQL on a dev question. Mechanism-blind.
- gated (B, D, E): first candidate passing neutral validity **and** the frozen gate.

**Slot failure is final.** No top-up to reach K. **All raw candidates are retained** and
generation reliability is reported separately from admitted-population quality.

**Artifact stability rule (new, from deviation D10):** a generation unit is complete only when
its JSON log exists, parses, and was published atomically. `gen_seed2.sh` writes generate.py
output to a temp path and renames on success; corrupt partials are treated as absent;
existing valid targets are skipped, never overwritten. Concurrent duplicate runs of one unit
are forbidden; where they already occurred, both versions are quarantined and the canonical
version is the **earliest complete finish with provable order — never selected by K_admitted**
(see `artifacts/phase2/quarantine/D_glm_s1/DECISION.md`).

**Builders (all primary, frozen):** glm=`GLM-5.3`, qwen=`Qwen3.8-Max`, deepseek=`DeepSeek-V4-Pro`,
kimi=`Kimi-K3`, minimax=`MiniMax-M3`, ernie=`ERNIE-5.0-Thinking-Preview`, all via
`llmapi.paratera.com/v1`. 6 builders × 3 seeds = **18 paired cells**. Any builder not in this
table is supplementary replication. API credentials come from the environment only;
hardcoding one is a P0 incident.

**Targets (frozen):** GLM-5.3-Flash (primary), Qwen3.8-Flash (second), DeepSeek-V4-Flash (third).

## 6. Conformance instruments (FROZEN)

Calibrated before any Phase-II outcome against known-good human implementations
(`hpc_repair`, `hpc_vote3`, `hpc_schema` — all must pass) and known-negative mutants
(`neg_uncond_twocall`, `neg_selectfirst` — both must fail), plus the invariant that **bare
must violate every conditional/content-based property**. `contract.py --calibrate` encodes
this as an executable gate (9/9) and must pass before any arm-E generation. The A–D
conformance semantics are frozen at commit `a87ced4` and are not modified in response to
candidate scores.

Key design points: paired counterfactual probes differing **only** in the varied condition;
exact normalized answer comparison (no substring); a first-query-succeeds variant separating
conditional repair from unconditional second calls; permutation-invariance detecting
positional selection without naming voting. Arm E additionally enforces **non-vacuity**
(contract must be violated by `bare.py`, run literally) and **conformance of only the
asserted** properties. Failed properties are never auto-dropped.

## 7. Primary estimand and inference

**Primary metric: bare-inclusive oracle headroom** on `split_p2_test`, official judge:

    H(P) = Acc( x ↦ max_{H ∈ P ∪ {H₀}} Y(x,H) ) − max_{H ∈ P ∪ {H₀}} Acc(H)

Total by construction: `H(∅) = 0`; `K = 1` is a genuine bare-vs-harness routing problem.
(Verified edge cases: K=0→0.0; K=1 complementary→0.2; a population with union_repair=1.0 can
have headroom 0.0 — which is why union repair is secondary.)

**Primary contrast: D − A, paired by (builder × generation seed).**

> **Primary hypothesis.** On the frozen untouched BIRD confirmatory set, the strategy-forced,
> behaviourally gated generation protocol (D) produces harness populations with greater oracle
> headroom over the best fixed option than unconstrained, ungated generation (A), under the
> official BIRD execution judge.

    H₀ : H(D) − H(A) ≤ 0        H₁ : H(D) − H(A) > 0

Reported as a point estimate, **two-sided 95% CI**, and paired permutation p-value. Continuous
effect sizes only; the Phase-I thresholds (union repair ≥ 15%, headroom ≥ 5 pp, ≥ 3 fix sets)
are a descriptive operational checklist and never label an arm a success or failure.

**No K-based exclusion.** Every pre-specified builder×seed cell enters regardless of admitted
population size, including K = 0 (a protocol that reliably produces nothing must score 0).
Excluding low-K cells conditions on a post-treatment outcome.

**Reported decomposition:** total effect `Δ_total = H_D − H_A` at nominal K, and K-controlled
effect `Δ_quality(k) = H_D(k) − H_A(k)` for k = 1 … K_min (200 random subsets). A separately
labelled population-conditional sensitivity (K ≥ 3 in both arms) may be reported.

**Confirmatory secondaries (Holm-corrected, tested after the primary):** gate main effect
`[(B−A)+(D−C)]/2`; strategy main effect `[(C−A)+(D−B)]/2`; **strategy × gate interaction**
`(D−C)−(B−A)` — the key mechanism result. All factorial secondaries run on
`split_p2_test_core`, with A and D restricted to those same 400 items.

**Secondary outcomes, in order:** union repair; pairwise disagreement; union harm;
`K_eff/K`; repair-set Jaccard. Then: builder differences, target transfer, conformance
profile, arm E (with its three rates: R_artifact, R_contract, R_fidelity). Mechanism
diversity `K_mech` is descriptive only, with no directional hypothesis.

**Inference:** hierarchical paired bootstrap — resample the 9 databases with replacement, then
tasks within each drawn database, and (builder × seed) cells with arms kept paired;
10,000 replicates; plus the paired permutation test. Task-level-only intervals may be
reported alongside, labelled conditional on realized populations.

## 8. Generation status at freeze (factual)

- A–D: seeds 0 and 1 complete for all 6 builders (24 + 24 = **48/72 units**); seed 2 = 0/24
  (generation interrupted; seed-2 partial raws quarantined; to be run via `gen_seed2.sh`).
- Arm E (separate track, not counted in the 72): 1 dev-side run (deepseek, seed 0) behind the
  calibrated gate, K=3/4, R_fidelity=0.50.
- Paired (builder × seed) cells with both A and D present: **12/18**.
- Confirmatory outcomes: none examined.

## 9. Failure taxonomy

- **M0 — generation null.** No distinct artifact (`SHA256 = bare`). All 40 old-protocol
  Qwen/DeepSeek candidates. The Phase-I "builder-independent collapse" claim over these is
  **retracted** as tautological.
- **M1 — mechanism absent** (Phase-I T1). **M2 — mechanism present, causal effect absent**
  (T2). **M3 — mechanism present but broken** (T3). **M4 — mechanism present,
  self-specification unfaithful** — *not established*; earlier arm-E evidence came from an
  under-powered gate and is void; the question is open.

The headline collapse claim concerns M1–M3 within genuinely distinct artifacts (day-1
population: 14 distinct sources, 12 PASS / 4 M1 / 3 M2 / 1 M3).

## 10. Deviation changelog (complete, merged from all prior protocol versions)

- **D1 (v1.1).** Phase-II collector smoke test ran against `split_p2_test` (2 items/database,
  18 items). Aggregate accuracies observed (bare 0.611, hpc_repair 0.722). No per-item outcome
  inspected, no protocol changed as a result. Items retained; dropping them would make the
  test set depend on the smoke test. All later pipeline testing uses `split_p2_dev`.
- **D2 (v1.2, from the first Codex adversarial review).** Fixed before any confirmatory run:
  cache key omitted model identity (target-transfer contrast silently erasable); collector
  shared one mutable harness instance across worker threads (corrupted `_trace`/`_call_seq`);
  official scorer had no real query timeout; conformance gate passable by no-ops (single
  scripted scenario, substring comparison) → rebuilt on paired counterfactuals; gate false
  negatives on result-based voting → stub DB returns SQL-dependent rows; `hint_guard`/
  `format_guard` are prompt-level by construction → declared contracts, not filename
  inference. "Old protocol 0/40 conform" reclassified **COPY_OF_BASELINE** (M0), retracting
  the builder-independence claim.
- **D3 (v1.2 SAP).** Four clarifications from the second design review: no K-based exclusion
  from primary (post-treatment conditioning); bare-inclusive headroom (K=0 defined, K=1
  meaningful); K-matching demoted to sensitivity over k=1…K_min with a population-conditional
  (K≥3) sensitivity; primary builder set frozen to all six named models; task-set allocation
  fixed (primary D−A on 1169; factorial secondaries on the 400-item core with A/D restricted
  to the same items).
- **D4 (v1.3).** Arm-E `branches_on_execution` verifier required the error *string* to reach
  a later prompt; the DSL text defines the property only as control flow depending on whether
  execution succeeded (error propagation is separately `carries_data_forward`). Specification/
  implementation mismatch; conjunct removed. Calibration re-verified 5/5; A–D untouched.
- **D5 (v1.4).** Arm-E probes under-powered, caught by known-good controls: carry probe ran
  only a success world (unfalsifiable for conditional repair); fail/ok probes converged,
  hiding execution-dependent filtering. Added failure-world carry probe and failing-majority
  probe. All prior arm-E results void; M4 withdrawn.
- **D6 (v1.5).** Paired probes differed in two respects at once (scripted response AND
  execution outcome), so `bare` falsely passed `branches_on_execution`. `S_OK` now
  byte-identical to `S_FAIL` except `fail_on`. Calibration invariant made an executable gate
  (`contract.py --calibrate`, 9/9) that must pass before arm-E generation.
- **D7 (re-confirmed).** Model identity in the cache key — first fixed in D2, violated again
  by concurrent duplicate queues during seed-1 recovery; re-verified in the unified scripts.
- **D8 (credential incident).** An API key was hardcoded in two sweep scripts and, worse,
  re-printed in the "fix" reports, re-committing the leak (commit `6f64f36`, and reports in
  `48fa0a6`). All working-tree occurrences redacted; secret scan (filenames only) now clean;
  untracked `.env` files verified untracked. **The credential must be revoked on the provider
  by the user; rotation is the only real remedy.** No new credential is to be given to any
  script until the sweep resumes.
- **D9 (script incident).** The rewritten sweep scripts passed `--out`, which `generate.py`
  does not define (units would fail at argparse), used `p2_`-prefixed JSON names incompatible
  with the monitor/yield tools, re-looped seeds 1–2 without skip protection (would have
  overwritten recovered seed 1), and masked Python failures with a trailing `echo`. All
  replaced by the single `gen_seed2.sh` (correct `--log`, `A_<builder>_s<seed>.json` naming,
  seed-2 only, skip-if-valid, non-zero exit on failure, temp-file atomic publish). Dry-run
  verified 24/24.
- **D10 (artifact divergence).** Two overlapping generation queues ran the same unit
  concurrently; `D_glm_s1.json` exists in two versions (repo: K=2/raw=22, committed
  16:09, matching the 16:05 recovery manifest; external: K=3/raw=20, rewritten at
  16:09:06 by a still-running duplicate). Both quarantined. Canonical = repo version by the
  earliest-complete-finish rule — *not* by K_admitted. Seed-1 reconciliation: 23/24 units
  source/repo identical (SHA-256, size, mtime in `seed1_reconciliation.json`). All queues
  were stopped (11 processes) before any further generation.
- **D11 (status misreporting).** Earlier state documents claimed "49/72", counting Arm E into
  the A–D grid; wrote a future date (2026-09-05) as the actual date; declared a "clean
  baseline / paused" state while generation processes were still running and artifacts were
  still being rewritten; and misstated the ICLR abstract deadline as Sept 19 (correct:
  **2026-09-18 11:59 PM AoE**; full paper 2026-09-25 AoE; no author changes after the
  abstract deadline). Corrected in this document.
- **D12 (collection timing; no analysis impact).** Mechanical outcome collection for the
  seed-0/1 A/D harnesses (119 harnesses + bare, frozen and hashed at anchor `98b95bf`)
  started on `split_p2_test` while seed-2 generation was still running. This deviates from
  the letter of "evaluation happens once, after generation completes" in order to overlap
  wall-clock. Scientific integrity is unaffected: the seed-2 generation process and its
  frozen gate cannot be influenced by these outcomes; the collected harnesses are exactly
  the frozen ones; **no aggregate metric, contrast, or analysis is computed until all 18
  paired cells are collected**. Exposure assessment was also corrected: the repository has
  **no remote** — the leaked key never left the local machine, so revocation is hygiene
  rather than an active breach (the earlier "already pushed" statement was unverified and
  wrong).

## 11. Residual blockers (owned, not claimed solved)

1. **Credential revocation — user action, outstanding.** Until the exposed key is revoked
   server-side, the incident is open regardless of tree cleanliness.
2. Seed 2 generation (24 units) not yet run; requires a valid environment credential and
   produces 18 paired cells only after completion.
3. Git history still contains the leaked key (commits `6f64f36`..`48fa0a6` region). History
   scrubbing is the user's decision; rotation is the effective remedy either way.
4. ICLR 2027 compliance (2027 template, mandatory AI-use disclosure, `\iclrfinalcopy` off,
   bibliography placeholders) — to be done during paper revision, before submission.
