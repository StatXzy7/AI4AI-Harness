# Phase-II Statistical Analysis Plan v2.0 — BLOCKING FIXES

This document supersedes the frozen SAP with MANDATORY corrections identified by the Codex
adversarial audit. Changes are minimal and surgical — only experiment-invalidating defects
are addressed, not "nice to have" improvements.

---

## Critical Changes from v1.0

### 1. Primary estimand is now CONTINUOUS, not binary admission

**v1.0 (BROKEN):**
> "D passes (headroom 7.95pp > 5pp threshold), A fails (4.64pp < 5pp)"

**v2.0 (FIXED):**
> "Primary estimand: paired difference Δ = H(D) - H(A), computed per (builder, seed) cell.
> Report mean Δ and 95% bootstrap CI. Threshold is operational checklist only, not inference."

**Why:** Point-estimate gates with overlapping CIs are sampling-noise roulette, not science.

**Implementation:** `outcome_table.py` already computes paired deltas — no new experiments.

---

### 2. Cache isolation is now MANDATORY per run

**v1.0 (BROKEN):**
> Cache key: `(prompt, system, temperature, n, seq)`

**v2.0 (FIXED):**
> Cache key: `(run_id, model, endpoint, prompt, system, temperature, n, seq, config_hash)`
> Phase-II starts from EMPTY cache, no carryover from Phase-I.

**Why:** Shared cache across models creates artificial outcome correlation (collapse by design).

**Implementation:** Already fixed in `generate.py` — verify no cross-run contamination.

---

### 3. Collector instantiates one harness per task

**v1.0 (BROKEN):**
> One harness per database, shared across concurrent worker threads

**v2.0 (FIXED):**
> One harness per (task, worker), with explicit state isolation

**Why:** Shared `_trace` and `_call_seq` across threads corrupts execution logs.

**Implementation:** Fixed in `collect.py:135` — audit whether old runs used broken version.

---

### 4. Official BIRD judge timeout is now ENFORCED

**v1.0 (BROKEN):**
> `sqlite3.connect(timeout=30)` — only locks, not execution

**v2.0 (FIXED):**
> `set_progress_handler` with wall-clock deadline, kills runaway queries at 30s

**Why:** Pathological SQL can hang evaluation indefinitely, diverging from BIRD's judge.

**Implementation:** Fixed in `official_scorer.py:62` — re-score pilot to confirm.

---

### 5. Conformance gate now uses COUNTERFACTUAL probes

**v1.0 (BROKEN):**
> `repair_v3` (first-succeeds) can pass without conditional branching — "call twice" passes

**v2.0 (FIXED):**
> v1/v2 (error cases) must produce DIFFERENT traces than v3 (success case). Unconditional
> second-call produces identical structure in all variants → fails.

**Why:** Single-scenario probes are trivially gameable.

**Implementation:** Fixed in `conformance.py:132` — already enforced, document in paper.

---

### 6. Touched registry is now FAIL-CLOSED

**v1.0 (BROKEN):**
> Scans only root JSONs and parquets, silently skips unreadable files

**v2.0 (FIXED):**
> Recursively scans ALL artifact formats (JSONL, CSV, notebooks, logs), reports `unscanned`
> list. Non-empty `unscanned` = registry INCOMPLETE, cannot be cited as provenance proof.

**Why:** "Scanner found nothing" ≠ "nothing exists" when the scanner has blind spots.

**Implementation:** Fixed in `touched_registry.py:63` — rerun before confirmatory.

---

## Non-Blocking Improvements (defer to paper revision if time-constrained)

### 7. Bootstrap at (builder, seed) level, not task level

**Issue:** Task bootstrap quantifies task uncertainty CONDITIONAL on realized harnesses.
It cannot support generalization claims about the generation protocol.

**Fix:** Pair (builder, seed) cells across arms, bootstrap those pairs, cluster tasks by database.

**Why:** The intervention is applied to populations, not tasks. Task bootstrap is pseudo-replication.

**Effort:** Medium — requires stats code rewrite, but no new experiments.

---

### 8. Report both judges, flag disagreements

**Issue:** Legacy judge (string coercion, 20K row cap) disagrees with official BIRD judge
in both directions.

**Fix:** Dual-score all results, report both, surface the delta.

**Why:** Transparency — hiding judge choice looks like cherry-picking.

**Effort:** Low — `official_scorer.py` already does this.

---

### 9. Arm E vocabulary is now FULLY generic

**Issue:** Current E prompt still mentions "mechanism" and "strategy", which are author terms.

**Fix:** Replace with pure trace primitives: "control flow", "data dependency", "branching",
"ordering". Zero mechanism names.

**Why:** E is supposed to test whether builders can discover mechanisms WITHOUT vocabulary injection.

**Effort:** Low — prompt rewrite only, no infrastructure change.

---

## Unchanged from v1.0 (still correct)

- Equal raw generation budget (R=3 per slot)
- Bare-inclusive oracle headroom as primary metric
- Primary contrast: D−A paired by (builder, seed)
- Admission: first candidate passing validity + gate (ungated) or validity + conformance (gated)
- Slot failure is final (no backfill to reach K)
- All raw candidates retained for reliability analysis

---

## Execution Checklist (before confirmatory evaluation)

- [ ] Verify cache namespacing is per-run isolated (check `generate.py:87`)
- [ ] Confirm collector uses per-task harness instantiation (check `collect.py:135`)
- [ ] Rerun `touched_registry.py` — confirm `"complete": true` in output
- [ ] Spot-check 5 generated harnesses pass counterfactual conformance probes
- [ ] Re-score pilot with fixed timeout (confirm no hangs on adversarial SQL)
- [ ] Audit: did ANY reported result use the old (broken) collector? If yes, RERUN.

---

## What This Does NOT Change

- Study design (2×2 factorial + arm E)
- Sample size (6 builders × 3 seeds)
- Metrics (disagreement, repair, harm, headroom, K_eff)
- Evaluation set size (1169 tasks from untouched test databases)

**This is a methods correction, not a redesign.**

---

## Version Control

v1.0: 2026-09-04 (frozen before Codex audit)  
v2.0: 2026-09-05 (incorporates blocking fixes only)  

Frozen commit: TBD (will be hashed and pushed before confirmatory evaluation starts)
