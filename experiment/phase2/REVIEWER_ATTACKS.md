# Phase-II Reviewer Attack Surface — Priority Fixes

This document lists the top vulnerabilities a strict ICLR reviewer will exploit, ranked by
lethality and remediation cost. Each item includes the attack, the current exposure, and
the cheapest defensible fix.

---

## BLOCKING ISSUES (must fix before submission)

### B1. Evaluation set contamination

**Attack:** "You developed the protocol on 24 tasks that are IN your confirmatory set, then
report significance thresholds on outcomes you've already observed. This is post-hoc analysis
dressed as preregistration."

**Current exposure:**
- 24/151 pilot tasks used for protocol diagnosis
- Human control designed after seeing those traces
- Admission thresholds adjusted from 20% → 15% after seeing results

**Fix:**
- NEW 1000+ task confirmatory set, completely untouched until all protocols frozen
- Relabel current 151 as "development set" in paper
- Report final results ONLY on the new set
- Cost: ~$12K API spend, 4 days collection time

**Status:** CRITICAL — this alone can sink the paper

---

### B2. "Forced diversity" is human-injected, not AI-discovered

**Attack:** "You claim AI generation restored diversity, but you actually hand-picked 8
different mechanisms and told the builder to implement them. The diversity comes from YOUR
strategy vocabulary, not the model's autonomous discovery."

**Current exposure:**
- Arm C/D prompts explicitly assign repair/vote/schema/hint/decompose/format/error/two-view
- The builder is a transcription service, not a discovery process

**Fix:**
- Reframe as "behaviorally explicit generation specifications prevent collapse"
- Add Arm E (already implemented): builder receives NO mechanism vocabulary, only generic
  trace primitives, and must both discover AND describe its own mechanism
- Report three rates: artifact validity, contract validity, self-fidelity
- Cost: Already built, just needs full 6-builder × 3-seed run (~200 generations, $500)

**Status:** HIGH — changes the paper's claim from "AI can restore diversity" to "structured
specifications can restore diversity", which is weaker but defensible

---

### B3. Point-estimate admission with overlapping CIs

**Attack:** "C has headroom 5.96pp [2.0, 8.6], threshold is 5pp. The CI crosses your gate.
You're admitting/rejecting based on sampling noise, not real effects."

**Current exposure:**
- Binary pass/fail based on point estimates
- Multiple populations have CIs that straddle thresholds
- Smells like p-hacking even when it isn't

**Fix:**
- Eliminate binary admission language entirely
- Report CONTINUOUS effect sizes: D−A repair delta, D−A headroom delta
- Threshold becomes "operational checklist, not scientific verdict"
- Primary inference is paired bootstrap CI on D−A difference
- Cost: Rewrite Section 5 + stats appendix, zero new experiments

**Status:** MEDIUM-HIGH — easy to fix, but failure to do so will draw "weak methods" criticism

---

### B4. Pre-specification is not actually pre-registered

**Attack:** "You initialized git history retrospectively on Sept 3, 2026, then cite 'frozen'
decisions by mtime. This isn't preregistration, it's an audit trail you control."

**Current exposure:**
- PHASE2_FREEZE.md repeatedly uses "pre-specified" and "frozen"
- Git history shows `2026-09-03 retrospectively initialized`
- No external timestamp (OSF, Zenodo, arXiv preprint)

**Fix:**
- Change all "pre-registered" → "pre-evaluation frozen internal protocol"
- Acknowledge in Limitations: "protocol decisions were frozen before Phase-II confirmatory
  evaluation, but not externally timestamped; an adversarial audit could question mtime
  authenticity"
- For THIS run (the real confirmatory one): generate protocol SHA256, push to public repo,
  tweet the hash BEFORE running any test evaluation
- Cost: Wording changes only, zero experiments

**Status:** MEDIUM — won't sink paper alone, but eliminates a credibility attack

---

### B5. Single-generation luck (no repeated seeds)

**Attack:** "You report one generation seed per builder. How do I know D's advantage isn't
sampling noise from lucky initial candidates?"

**Current exposure:**
- Original pilot: 1 seed per builder per arm
- New plan: 3 seeds, but not yet executed

**Fix:**
- Run 3 independent generation seeds per (builder, arm)
- Report seed-aggregated means + seed-level variance
- Show per-seed headroom values in appendix
- Cost: 3× generation budget (~$1,500 for 6 builders × 4 arms × 3 seeds × 8 harnesses)

**Status:** HIGH — SAP already specifies this, must actually do it

---

### B6. Cache-induced coupling creates collapse

**Attack:** "Your cache key omits model ID. DeepSeek and Qwen can receive each other's
cached responses. You didn't measure collapse — you CAUSED it by forcing different harnesses
to share responses."

**Current exposure:**
- Cache key is `(prompt, system, temp, n, seq)` — no model ID
- Phase-II changes SOLVER_MODEL while reusing old cache
- Partial fix already deployed (per-run cache namespacing)

**Fix:**
- Confirm cache namespacing is FULLY isolated per (model, run_id, config_hash)
- Rerun cache-sensitivity analysis: take 200 tasks, repeat with independent randomness vs
  common-random-numbers, measure outcome covariance
- Cost: ~$800 for 200-task × 10-harness × 3-repeat matrix

**Status:** MEDIUM — partially fixed, but needs empirical cache-effect quantification

---

### B7. Collector thread-safety bug corrupts traces

**Attack:** "Your collector shares one harness instance across worker threads. `_trace` and
`_call_seq` are not thread-safe. You've been collecting garbage data."

**Current exposure:**
- `collect.py:123` creates one harness per DATABASE, reused across tasks
- Concurrent calls write to shared state
- Already fixed in latest version, but old runs may be contaminated

**Fix:**
- Audit: check whether any confirmatory run used the old collector
- If yes: rerun collection with per-task harness instantiation
- If no: document the fix date and confirm all reported results use fixed version
- Cost: Potentially full re-collection (~$10K if BIRD matrix is invalidated)

**Status:** BLOCKING if old data is used, RESOLVED if only new collector ran

---

## HIGH-PRIORITY (strongly recommended)

### H1. Single domain limits generalization claim

**Attack:** "This is a BIRD-specific finding. Maybe text-to-SQL has unique properties that
make collapse inevitable."

**Fix:** Cross-domain replication (see CROSS_DOMAIN_PLAN.md)
- Cost: ~$6,500 + 1 week
- Status: Already planned, HIGH priority

---

### H2. Single target family limits transfer claim

**Attack:** "You only test GLM-to-GLM transfer. Show me harnesses built for Qwen improving
a DeepSeek target, or admit this doesn't transfer."

**Fix:**
- Evaluate D population on 4 targets: Qwen (mid), DeepSeek (strong), GPT-5.6 Sol (frontier),
  Claude Opus 5 (frontier)
- Report per-target headroom + harm
- Cost: 4× target evaluation, ~$3K incremental

---

### H3. Routing failure is under-investigated

**Attack:** "You claim diversity is necessary but not sufficient, then report one AUROC
number. Where's the analysis of WHY routing failed?"

**Fix:**
- Task-held-out, database-held-out, harness-held-out, joint-holdout splits
- LLM-as-value-predictor baseline (Sol/Opus)
- AUPRC (not just AUROC) for imbalanced repair labels
- Selective risk-coverage curves
- Cost: ~$2K for LLM baseline, rest is post-processing

---

### H4. Builder generalization is weak (N=3 originally, now N=6)

**Attack:** "Three builders is not evidence of generalization."

**Fix:** 6 builders already planned (GLM, Qwen, DeepSeek, Kimi, MiniMax, Ernie)
- Cost: already budgeted
- Status: In progress

---

## MEDIUM (nice to have, not blocking)

### M1. Official BIRD evaluator timeout is broken

**Attack:** "You claim to use the official judge, but your implementation doesn't actually
timeout long-running queries."

**Status:** FIXED — `set_progress_handler` now enforces wall-clock limit
- Rerun re-scoring on pilot data to confirm
- Cost: Zero (offline re-scoring)

---

### M2. No uncertainty quantification on routing

**Current:** Single AUROC point estimate  
**Fix:** Bootstrap CI on AUROC/AUPRC  
**Cost:** Post-processing only

---

### M3. Conformance gate is gameable

**Attack:** "A harness that always calls twice passes repair_v3 without ever reading errors."

**Status:** FIXED — counterfactual probes now enforce that v3 (first-succeeds) produces
different trace than v1/v2 (first-fails)
- Document the fix in paper
- Cost: Zero

---

## REMEDIATION PRIORITY QUEUE

**By Sept 7 (before confirmatory evaluation):**
1. [B1] New untouched 1000-task confirmatory set
2. [B5] 3 generation seeds per cell
3. [B6] Cache isolation + sensitivity analysis
4. [B7] Audit collector thread-safety in old runs
5. [B2] Arm E full run (6 builders × 3 seeds)
6. [B3] Continuous effect sizes, eliminate binary admission
7. [B4] Public protocol hash before evaluation

**By Sept 15 (before paper writing):**
8. [H1] Cross-domain replication (SWE-bench)
9. [H2] 4-target transfer matrix
10. [H3] Routing deep-dive

**By Sept 23 (final polishing):**
11. [M1-M3] Documentation + post-processing

---

## Cost Summary

| Item | Cost | Time | Blocking? |
|------|------|------|-----------|
| B1 new confirmatory set | $12K | 4d | YES |
| B5 3 seeds | $1.5K | 2d | YES |
| B6 cache analysis | $0.8K | 1d | MEDIUM |
| B2 Arm E | $0.5K | 1d | HIGH |
| H1 cross-domain | $6.5K | 7d | HIGH |
| H2 4-target transfer | $3K | 2d | HIGH |
| H3 routing deep-dive | $2K | 3d | MEDIUM |
| **TOTAL** | **~$26K** | **~20d** | |

**Current budget status:** Unknown — need user confirmation before proceeding with $26K spend.

**Minimum viable defense (blocking only):** $14.8K + 8 days
