# Final review (round 3) — verify PARTIAL closures + final numbers

You are the independent reviewer (different model from implementer) for
AI4AI-Harness. Repo E:/projects/AI4AI-Harness. Read-only; do not edit.

In round 2 (gpt-5.6-sol) you returned APPROVE_WITH_CHANGES with two PARTIAL:
- R1-6: merge keeps first-completed on doubly-executed conflicts.
- R1-9: no explicit lambda=1 U_b scalar; missing call evidence defaulted to zero.

The NEW MEDIUM was: final seal and number regeneration outstanding.

Verify all three are now closed against the current tree:

1. **R1-9**: experiment/revision/wp2r_selector.py now emits
   `U_b_lambda1_net_vs_bare` (mean net (Y_pi - Y_bare)) inside each E_b
   policy, and treats a member-task with NO call-evidence key as
   non-compliant (falls back to bare), never as zero calls. Confirm the
   implementation matches the Class-E formalization in
   paper/latex/sec_appendix.tex (lambda=1, b=3) and that the final
   artifacts/wp1r_20260915/wp2r_selector_report.json numbers are coherent
   (pi_Z/bare/dev-fixed all 94.96% with zero repair/harm; random_fixed
   85.14%, -10.12pp vs dev-fixed CI [-13.27,-7.22], U_b net -10.04pp,
   harm 0.1637 > repair 0.0327).

2. **R1-6**: the 5 real-arm doubly-executed conflicts have a frozen
   exclusion sensitivity (E2_sensitivity_double_executed_conflicts) and
   its D matches the primary to two decimals (both ~0.15pp, CIs overlap).
   Confirm in analysis_report.json that retaining first-completed cannot
   change the verdict. Dev arm's 2 conflicts are likewise reported.

3. **Final seal/numbers**: all three arms sealed
   (SEALED_eval_real/eval_clone/dev_real.json; 10800/10800/2700; 0
   run_invalid; 0 source drift). wp1r_numbers.tex and
   wp1r_policy_table.tex are regenerated from the sealed JSONs (check a
   few values match). Paper sec_wp1r.tex reports the final numbers.
   Restore tool experiment/revision/restore_usage_unknown.py recovered
   answers preserved on closed usage-unknown cells (frozen preserve-answer
   policy) with tests in test_restore_usage_unknown.py — confirm it cannot
   restore a genuine http_unknown cell (test asserts this).

4. Build: paper main text content ends on page 9; page 10 begins the
(non-counted) ethics/repro/AI statements; 0 undefined refs. Confirm by
inspecting paper/latex/main.pdf.

Give: R1-6 verdict, R1-9 verdict, NEW-MEDIUM verdict (FIXED/not), any new
issues, then final line `VERDICT: APPROVE|APPROVE_WITH_CHANGES|BLOCK`.
Be concise; investigate only what you must.
