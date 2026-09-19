# Independent review request (read-only)

You are the independent reviewer for the AI4AI-Harness ICLR 2027 submission. You did NOT write these changes. Review them adversarially but fairly. Do not edit any files.

## Context

The paper (paper/latex/) studies evaluation of AI-generated LLM harness populations. An ICLR program-chair review raised weaknesses; the diffs below are the author's revisions addressing them:

1. `paper_edits.diff` — LaTeX revisions addressing reviewer points:
   - W2/W3: added HarnessForge (arXiv:2606.01779) and LLM-as-a-Verifier (arXiv:2607.05391) discussion + mutation-testing citations (Budd & Angluin 1982, Papadakis 2019 survey) + ReAct citation (Yao 2023) + repeated-sampling baseline (Chen 2021 codex).
   - W7: clarified free-arm slot allocation (8 independent generations of the same free prompt) and the II-B gate mechanism (mandatory MECHANISM declaration from a 4-word vocabulary: repair/vote/twostage/plain, verified against traces); noted free declarations are narrower than forced contracts so arm-B populations are not nested in arm-A.
   - W8: formalized Class D (frozen pre-execution policy pi_Z, paired per-task difference vs dev-fixed) and Class E (budgeted utility with lambda=1 harm weighting, admissible only with per-record budget evidence).
   - W5: added finite-repeat Jensen-bias paragraph (cross-fitted discovery/validation + same-code clone null carrying identical bias + hash-refusal gates).
   - W6: reported pre-specified Arm II-E outcomes (dev-side only: 10 raw attempts, 3/4 slots admitted, R_fidelity 0.5, never evaluated on confirmatory split; earlier pilot voided by deviations D4-D6).
   - R3 audit details added to appendix (bare-only, 3 cache-off repeats, core-400, 58/400 any-flip, pairwise 39/40/37).
   - T1 worked example added (cand_bird_g1_b0r0_g0: docstring claims token cap, control flow identical to bare, 0 SQL executions on 10/10 audited tasks, final SQL byte-identical to bare on 6/10).
   - Stratification variables for the 400-item core (proportional allocation across 9 databases, seed 20260904, no difficulty/outcome variable).
   - 432-attempt cap arithmetic (18 cells x 8 slots x <=3 attempts).
   - Primary estimand rationale (D-A diagonal = joint deployed intervention).
   - Seed resampling limitation (3 seeds/builder).
   - Control-authoring/review models added to model inventory (GPT-6 dev, gpt-5.5 / gpt-5.6-sol authoring/review).
   - MATH dev split clarification (100 dev = smoke-only; policy training uses first 80 of 400 eval tasks, leaving 320 scored).
   - 24->12 control mapping (12 classes x 2 instances; calibration=instance 1, blinded=instance 2 + 2 auditor challenges).
   - H(P) equation formalized; (u)_+ defined; 0.938->0.9375 precision; missing closing paren fixed.

2. `code_edits.diff` — Python changes to experiment/revision/wp1r_analysis.py and wp2r_selector.py:
   - merge_cells(): merges continuation ledgers (collection was split across ledgers by two provider-timeout stops). Precedence: completed observation beats unknown_remote; among completed, earliest ledger wins; both-completed-disagree cells recorded in a dedup report.
   - matrices() now accepts ledger lists, verifies continuation manifests share frozen execution fields (raises on mismatch), returns a 7-tuple.
   - accounting() dedups migration copies by (key, official_correct, accounting) signature; distinct re-executions count individually.
   - sqlite connections now explicitly closed (Windows file-lock fix).
   - New test file experiment/revision/test_wp1r_merge.py (6 tests, all passing).

## Your task

Review and report findings ranked by severity (CRITICAL/HIGH/MEDIUM/LOW):

A. **Factual accuracy**: Do the new LaTeX claims match the evidence quoted above and general scientific correctness? Flag any claim that overstates, any citation used incorrectly (e.g., is Budd & Angluin 1982 Acta Informatica correct for the equivalent-mutant problem? Is Chen et al. 2021 appropriate as the repeated-sampling baseline reference?), any internal inconsistency with the rest of the paper (you may read the full files in paper/latex/ for context).

B. **Statistical correctness**: Is the merge precedence rule sound for the outcome matrix? Does the dedup logic risk biasing the analysis (e.g., survivorship, preferring earlier ledgers)? Is the Jensen-bias mitigation description accurate (cross-fitting + clone null carrying identical bias)? Is the accounting dedup correct?

C. **Completeness vs the reviewer points**: Given the reviewer points listed above, is anything addressed incorrectly or left ambiguous?

D. **LaTeX/style**: any broken constructs, undefined references, or notation clashes with the rest of the paper (check sec_diagnostics.tex, sec_results.tex, sec_appendix.tex for consistency).

The diffs are at /tmp/paper_edits.diff and /tmp/code_edits.diff (also readable as C:/tmp paths may not exist — if not, use `git diff -- paper/latex/...` and `git diff -- experiment/revision/...` in the repo at E:/projects/AI4AI-Harness). Report findings as a numbered list with severity, file, and one-line fix suggestion. End with an overall verdict: APPROVE / APPROVE_WITH_CHANGES / BLOCK.
