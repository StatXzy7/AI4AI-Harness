# Gate-v3 independent finite controls: premeasurement protocol

2026-09-10. Instrument developer/executor GPT-6; fresh-context control author gpt-5.5; fresh-context adjudicator gpt-5.6-sol. Backend build identifiers beyond these tool-visible model names are unknown. Scope is new, independently authored synthetic controls, not model generation, benchmark testing, production admission or population error-rate estimation.

## Authoring and freeze

Freeze gate-v3 and the public CONTRACT.md before author dispatch. The author reads only this protocol and CONTRACT.md. Do not expose instrument code, prior control code, prior packets, measurement results, manuscript results or repair logs. Author 32 cases: eight mechanism types, two intended conforming and two intended nonconforming implementations per type. Positive implementations should use distinct program organizations; negatives must violate a relevant contract requirement. Prohibit special-casing probe names, salts, marker values, expected synthetic SQL or control IDs.

Author writes `experiment/revision/independent_gate_v3_controls.py` with CASES entries containing only case_id/strategy/solve, IDs vc001-vc032. Separate author_labels.json contains reference labels and reasons; these are fallible intended labels, not assumed truth. Syntax/AST validation is allowed; do not run the instrument before source and labels are frozen. No correcting a case after its first measured behavior. Retain any execution failures and reference disagreements, with a new version required for later revisions.

After authoring, freeze exact instrument, controls, runner, contract, protocol and label hashes plus ordered case roster. Evaluate each case once with salt `independent-v3-20260910`. Salt changes existing synthetic markers, not probe coverage. Require results, complete neutral review packet and COMPLETE.json hash agreement. Preserve unknown/additional probe traces. A packaging-only recovery may read saved results but cannot rerun evaluate. Do not automatically retry a started measurement.

## Independent review and fixed merge

The adjudicator may read only this protocol, CONTRACT.md, and the neutral review packet (full control source and all question/schema/request/response/execute/final/error fields). Withhold author labels, automatic verdicts/reasons, instrument implementation and all old evidence. Do not show instrument-generated decomposition attribution metadata; only observed API request/response fields belong in the neutral packet.

All32 cases receive independent source-contract verdicts. All20 cases in hint_guard, format_guard, two_view, error_classify, decompose additionally receive semantic/data-flow verdicts, including structural failures and passes; the other12 have semantic verdict null. Each verdict requires exact source or typed trace evidence. Source-contract review is about code behavior; semantic review is about the declared mechanism, not whether scripted SQL solves a real task. Maximum one evidence/record clarification round; retain initial adjudication, any changed verdicts and reasons. Never change instrument, controls or original author labels in this round.

Merge rules, fixed before measurement:

1. Structural fail/execution_failure is retained as such even if semantic review is conforming or indeterminate.
2. For the five semantic groups, pass/review_required plus semantic conforms becomes hybrid_conforms; semantic nonconforms becomes hybrid_nonconforms; indeterminate stays unresolved. No automatic pass bypasses these reviews.
3. For repair/vote3/schema_link, pass becomes structural_conforms; an unexpected review_required stays unresolved. Do not assume a missing review is positive or negative.
4. Keep author/source-review disagreements (including source indeterminate) as disputed and outside right/wrong counts, while reporting all32 cases and original author-reference totals. Do not repair these labels to improve measured performance.
5. No combined result is a production admission. Only undisputed reference cases support this finite control comparison. Report cases and counts by type/state, not inferred population false-positive/false-negative rates or confidence intervals from this nonrandom balanced set.

## Finite acceptance criterion

The finite check is not ready if any undisputed conforming reference is rejected, any undisputed nonconforming reference is accepted, any execution failure or unresolved case remains, or any mechanism lacks two undisputed conforming and two undisputed nonconforming references. Reference disputes are preserved and can cause incomplete coverage. All32 matching would support only this finite sample and interface, not general calibration, B completion or overall paper clearance.

Any subsequent instrument repair needs a new version and new independent controls. This batch becomes exposed after measurement. Paid/provider generation requests and benchmark evaluations remain zero for this stage; application agent compute is not asserted to be zero cost. Scientific A-D and W1 requirements remain intact.
