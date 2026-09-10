# Review Request: Two Post-Hoc Analyses + Cross-Domain Mini-Audit (2026-09-08)

Reviewer: Codex (adversarial, cross-model). Executor: ZCode (Claude Opus 4.8).
Scope: verify the claims below against the named artifacts and attack the
methodology. REPORT format: per item — CONFIRMED / ATTACKED (with reason) /
INSUFFICIENT EVIDENCE.

## Item 1: W3 rich behavioral fingerprint (post-hoc, zero new API calls)

Script: `experiment/phase2/w3_fingerprint.py`
Output: `artifacts/phase2/w3_fingerprint.json`
Data: 384 p2 harnesses (18 cells), core-400 cached outcomes; R2 cache-off
replication for rerun stability.

Claims to verify:
1. On cells where a within-cell harness pair AGREES on the verdict, 76.6% emit
   different normalized final SQL (mean token Jaccard 0.69).
2. Spearman between mean SQL dissimilarity (computed on verdict-AGREEING cells
   only) and overall outcome disagreement: 0.59 all pairs, 0.57 within-arm
   (1,010 pairs). Phase-I code similarity was -0.01. Interpretation offered:
   output-space similarity carries signal that code-space similarity lacks.
3. Rerun stability (same harness, cached vs cache-off): n_llm_calls changes
   1.8%, verdicts 8.5%, final SQL 70.0% (mean token Jaccard 0.62 when changed).
   Interpretation offered: richer channels are noisier channels; the verdict
   channel is the most stable behavioral signal.
4. Per-arm cost: multi-call fraction A .298 / B .245 / C .422 / D .392;
   mean accuracy A .641 / B .644 / C .620 / D .620. Interpretation offered:
   forced mechanisms execute (more calls) yet score lower.
5. Consistency: among 365,095 pair-cells with identical normalized SQL, verdict
   disagreement is exactly 0.

Known caveats we already plan to disclose:
- SQL normalization lowercases outside string literals only (literal case is
  verdict-relevant: 'Eur' vs 'EUR' flips the official BIRD judge).
- Exploratory/post-hoc on already-analyzed confirmatory outcomes.

## Item 2: W1 diversity-aware population selection (post-hoc, zero new API calls)

Script: `experiment/phase2/w1_selection.py`
Output: `artifacts/phase2/w1_selection.json`
Design: 18 cells (pools 9-29 harnesses, arms mixed), task split by random
database halves, 100 splits; selection on dev only; held-out evaluation;
cell-level bootstrap (18 cells) over split-averaged paired deltas.

Claims to verify:
1. k=8: div-only (greedy max dev oracle coverage) vs top-acc (top-8 dev
   accuracy): +0.82 pp held-out headroom, 95% CI [0.43, 1.31].
2. k=8: div-only vs random (mean over 200 draws): +0.40 pp, CI [0.18, 0.66].
3. k=8: random vs top-acc: +0.41 pp, CI [0.19, 0.68] — accuracy selection
   is worse than random.
4. k=4: +0.65 [0.23, 1.17] vs top-acc; +0.24 [-0.03, 0.53] vs random (NOT
   distinguishable from random at k=4 — disclosed).
5. Claimed interpretation: population-level statistics transfer across the
   database split; per-item value estimates do not (ties to the existing
   sec_boundary LOHO result).

Attack surfaces we want probed:
- Post-hoc selection of the dev/test split AFTER seeing confirmatory results.
- Arm-mixed pools (a real deployment population is single-arm).
- The λ-sweep reporting (only div dominates; is that cherry-picked?).
- Multiple comparisons across (k, method) grid.

## Item 3: Cross-domain mini-audit protocol (RUNNING at time of writing)

Pipeline: `experiment/gsm8k/` (harness_base, generate, collect, metrics).
Frozen split: `artifacts/gsm8k_audit/math500_split.json` (MATH-500, 500 tasks:
100 dev + 400 eval; seed 20260908).

Protocol decisions to review (before results exist, so protocol can still change):
1. GSM8K was REJECTED for the audit: bare GLM-5.3-Flash = 0.993 on 150 eval
   tasks (ceiling; no disagreement space). Artifact: run_bare.jsonl.
2. MATH-500 chosen: bare = 0.9175 (judge-validated: 400/400 golds judge
   correct against themselves; run_bare_math500.jsonl, re-scored).
3. Free-arm protocol only (arm A analogue): 6 builders x 8 slots, R=3 raw
   attempts/slot, neutral validity gate (mechanism-blind). No factorial, no
   conformance gate — replication probe of the Phase-I phenomenon only.
4. Judge: numeric equality when both parse (incl. \frac{a}{b}, a/b, decimals),
   else normalized LaTeX string equality (units/base-subscripts/^\circ stripped,
   pmatrix->tuple, \text{} content preserved). Single judge, no official/legacy
   duality. Known limitation: residual judge misses ~1-2% of answers (e.g.
   '3+2√2, 3−2√2, ...' vs '3 ± 2√2' style mismatches).
5. Target frozen: GLM-5.3-Flash (same as SQL paper).
6. Solver cache: shared gsm8k cache file, keyed on (model, base_url, prompt,
   system, temp, n, seq) — identical prompts across harnesses intentionally
   collapse to one cached reply (same convention as the SQL confirmatory run).
7. Yield so far: 42/48 slots admitted (glm 4/8, qwen 6/8, others 8/8).
   R_artifact 0.21 (glm) to 1.0 (kimi).

Questions for the reviewer:
- Is bare=0.9175 (8.25% error) sufficient disagreement space for a collapse
  audit, or should the eval be restricted to level 4-5 items?
- Any objection to the single-judge design given the disclosed normalizer?
- Should the audit report include a no-cache replication (like R2) given the
  shared cache convention?

## Paper edits already made (for context)

- sec_results.tex: new subsection 5.4 "Exploratory: what to measure, and what
  to select for" (compact; details in appendix).
- sec_appendix.tex: new section "Exploratory Fingerprint and Selection
  Analyses" (app:rich).
- sec_discussion.tex / sec_conclusion.tex: "What to measure, then" guidance +
  selection recommendation; Limitations extended (exploratory status).
- Main text held at 9 pages (figures shrunk, prose tightened).

---

## UPDATE (2026-09-10): cross-domain mini-audit complete

The audit finished (35/48 slots admitted, 400 eval tasks, 14,000 rows).
Final metrics (artifacts/gsm8k_audit/metrics.json):
- mean pairwise disagreement 10.6%, K_eff 33/35, outcome-identical pairs 0.7%
- union repair over bare 76.0%, union harm 0.8%, oracle headroom over bare 4.75pp
- best fixed member is bare itself (0.9375); generated harnesses 0.68-0.87

Protocol deviation to review (disclosed in artifacts/gsm8k_audit/PROTOCOL_CHANGELOG.md,
entry G1): the first generation round used a GSM8K-style task description that
mismatched MATH-500's LaTeX answers; all first-round data was quarantined as a
pilot and generation rerun. The pilot supplies a controlled contrast
(population remains diverse at 16.2% disagreement while union repair collapses
to 18% - a prompt-side protocol error invisible to code checks, killing
utility without killing diversity).

Questions added for the reviewer:
- Is the G1 disclosure + quarantine handling acceptable, or must the pilot be
  dropped entirely?
- The cross-domain claim is "clean-protocol diversity replicates" (NOT "collapse
  replicates" - we did not rerun the collapse-inducing protocol). Is that the
  right claim boundary?
