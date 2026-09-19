# Independent review — Round 2 (verify fixes)

You are the same independent reviewer (different model from the implementer). In Round 1 you returned BLOCK with 13 findings (3 CRITICAL, 6 HIGH, 3 MEDIUM, 1 LOW) on the AI4AI-Harness ICLR 2027 revision. Verify the fixes below adversarially: confirm each is actually fixed in the current working tree (repo E:/projects/AI4AI-Harness), and raise any NEW regression introduced by the fixes. Do not edit files.

The current diffs: `/tmp/code_edits2.diff` (experiment/revision/wp1r_analysis.py, wp2r_selector.py, wp1r_seal.py, wp1r_render.py, test_wp1r_merge.py) and `/tmp/paper_edits2.diff` (paper LaTeX). Two new untracked files are NOT in the diff — read them directly: `paper/latex/sec_wp1r.tex` and `paper/latex/sec_app_wp1r.tex`.

## What was done for each Round-1 finding

**R1-1 (CRITICAL): A8.6 paired D compared different task lists.**
`a86_statistic` now also returns the complete-case column indices; `a86_test` intersects both arms' task columns and computes D + bootstrap CI on the intersection (`n_tasks_paired`). A_real/A_clone stay arm-specific as the frozen protocol defines. Check: is the pairing now correct? Is the permutation null untouched and valid?

**R1-2 (CRITICAL): missingness gate not enforced.**
Added frozen `MAX_EXCLUDE_FRAC = 0.10`; if either arm excludes >10% the verdict becomes INSUFFICIENT (coverage) with the exact fractions reported (`excluded_frac_real/clone`). Also added the frozen within-task repeat-mean imputation sensitivity (`sensitivity_imputed`) per protocol. Check: does the gate logic match the protocol text in review-stage/REAL_EVIDENCE_PROTOCOL_V1.md (the A8.6 缺失规则 section)?

**R1-3 (CRITICAL): Jensen-bias paragraph overstated.**
Text now says "positive-bias risk", strict only when finite-R noise can change the argmax, and the clone null removes "the shared component of the bias without assuming exact cancellation". Check sec_diagnostics.tex Finite-repeat bias control paragraph for mathematical correctness.

**R1-4 (HIGH): cross-fitting leakage in fit_pi_z.**
dev-accuracy feature is now computed per fold from training rows only (`Y_tr[:, tr].mean(axis=1)` inside the fold loop). New regression test `SelectorLeakageTest` spies on the fitted design matrix and asserts fold features never equal all-dev means. Check the fix and the test.

**R1-5 (HIGH): accounting dedup over-collapsed.**
Dedup signature is now the FULL cell record json (incl. worker_pid, trace, final_answer, accounting), so only byte-identical migration copies collapse; distinct executions always count. New test `test_full_record_identity_dedup`. Verify.

**R1-6 (HIGH): merge survivorship + state conflation.**
merge_cells now reports a `terminal_states` histogram (completed/failed/unknown_remote) and a frozen sensitivity branch `matrices(..., conflict_policy='nan')` that excludes the 5 doubly-executed disagreeing cells instead of first-completed; main() reports `E2_sensitivity_double_executed_conflicts` (D, CI, n excluded) and the appendix discloses the rule. Check whether this adequately addresses survivorship or whether first-completed is still biased; report any residual concern.

**R1-7 (HIGH): manifest validation too narrow.**
matrices now compares solver, cache_mode, temperature_semantics, judge, protocol, section, repeats, harnesses, panel_draw, tasks_sha256, split_sha256, schedule_sha256, task_order; only acquisition_id/concurrency/global_budget/protocol_sha256 allowed to differ (documented amendments). Check this field list for holes.

**R1-8 (HIGH): R3 "nondeterminism floor" wording.**
Appendix app:r3 now says "observed instability rate ... not a standard error or an effect-size floor ... sets the scale at which repeat controls become necessary". Check.

**R1-9 (HIGH): E_b not really computed.**
wp2r_selector now computes per-member worst-case logical calls per eval task from the merged ledgers (`load_eval_call_counts`), enforces b=3 per policy choice with bare fallback on violating tasks, and reports accuracy/violations/repair/harm per policy. (Cannot fully run until dev_real collection finishes, but read the code.) Check correctness of the harm weighting (lambda=1) and whether it now matches the Class-E formalization.

**R1-10 (MEDIUM): probabilistic pi_Z but no expectation.**
Class D now says "single deterministic mapping". Check consistency with the selector implementation (argmax + abstention is deterministic).

**R1-11 (MEDIUM): II-B gate ambiguity.**
sec_phase2 now says the free-arm gate is "an operational mapping, not an independently calibrated contract". Check against the appendix gate-controls scope text.

**R1-12 (MEDIUM): related-work comparisons too strong.**
HarnessForge sentence softened to "raises two practical costs that motivate our diagnostic"; LLM-as-a-Verifier sentence now states the information-set difference (post-execution trajectory scoring vs pre-execution selection). Check.

**R1-13 (LOW): citations adjacent not exact.**
Chen et al. now described as pass@k sample-level analogue with our clone control explicitly called "the execution-level analogue for a fixed harness"; Budd1982/Papadakis2019 framed as adjacent program-equivalence/equivalent-mutant work. Check.

## Also check
- `wp1r_seal.py` new `--merged` seal path (excludes the legitimately-evolved collector hash from the drift check, still checks all measured sources + cross-ledger consistency).
- New unit test file (11 tests) covers: merge precedence, manifest mismatch, matrices shapes, full-record accounting dedup, A8.6 task intersection, coverage gate, imputation sensitivity, fold leakage.
- The paper builds (0 undefined refs).

Give per-finding verdict: FIXED / PARTIAL / NOT_FIXED / NEW_ISSUE, with one-line evidence. Then any NEW issues ranked by severity. End with overall verdict: APPROVE / APPROVE_WITH_CHANGES / BLOCK.
