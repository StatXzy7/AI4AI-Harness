R1-11: FIXED — II-B is labeled operational rather than independently calibrated (`paper/latex/sec_phase2.tex:23-29`).
R1-12: FIXED — HarnessForge and post-execution verifier comparisons are scope-qualified (`paper/latex/sec_related.tex:16-20,84-91`).
R1-13: FIXED — Adjacent citations and the clone-control analogy are explicitly bounded (`paper/latex/sec_related.tex:97-102`).
NEW issues: MEDIUM — Final seal and number regeneration remain outstanding; current selector macros/table are placeholders (`experiment/revision/wp1r_render.py:56-63,150-159`; `paper/latex/wp1r_policy_table.tex:1-3`). No code defect currently blocks that final run.
VERDICT: APPROVE_WITH_CHANGES
R1-1: FIXED — Paired \(D\) now uses the complete-task intersection (`experiment/revision/wp1r_analysis.py:279-303`).
R1-2: FIXED — 10% exclusion gate and imputation sensitivity are enforced (`experiment/revision/wp1r_analysis.py:320-365`).
R1-3: FIXED — Jensen/clone-null wording is properly qualified (`paper/latex/sec_appendix.tex:669-678`).
R1-4: FIXED — Fold features use training rows only, with a leakage spy test (`experiment/revision/wp2r_selector.py:75-86`; `test_wp1r_merge.py:119-155`).
R1-5: FIXED — Accounting deduplication uses the full record identity (`experiment/revision/wp1r_analysis.py:398-405`).
R1-6: PARTIAL — Terminal states and conflict-exclusion sensitivity exist, but the primary merge still retains first-completed outcomes (`experiment/revision/wp1r_analysis.py:90-160,449-475`).
R1-7: FIXED — Continuation manifests compare all frozen solver, harness, split, schedule, and task fields (`experiment/revision/wp1r_analysis.py:166-177`).
R1-8: FIXED — R3 is explicitly described as observed instability, not an SE or effect-size floor (`paper/latex/sec_appendix.tex:184-194`).
R1-9: PARTIAL — \(b=3\) fallback and repair/harm reporting are implemented, but no explicit \(\lambda=1\) \(U_b\) scalar is emitted and missing call evidence defaults to zero (`experiment/revision/wp2r_selector.py:201-233`).
R1-10: FIXED — Class D is now a deterministic pre-execution policy (`paper/latex/sec_diagnostics.tex:44-48`).
R1-11: FIXED — II-B is labeled operational rather than independently calibrated (`paper/latex/sec_phase2.tex:23-29`).
R1-12: FIXED — HarnessForge and post-execution verifier comparisons are scope-qualified (`paper/latex/sec_related.tex:16-20,84-91`).
R1-13: FIXED — Adjacent citations and the clone-control analogy are explicitly bounded (`paper/latex/sec_related.tex:97-102`).
NEW issues: MEDIUM — Final seal and number regeneration remain outstanding; current selector macros/table are placeholders (`experiment/revision/wp1r_render.py:56-63,150-159`; `paper/latex/wp1r_policy_table.tex:1-3`). No code defect currently blocks that final run.
VERDICT: APPROVE_WITH_CHANGES
