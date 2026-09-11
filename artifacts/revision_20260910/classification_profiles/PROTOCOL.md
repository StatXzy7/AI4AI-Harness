# Classification response profiles: exposed-control development regression

Stage21, 2026-09-10. This protocol is fixed before profile execution. It does not replace gate-v3, its independent measurements, or the original reference labels. No provider generation or benchmark evaluation is authorized by this document.

## Source-only role assignment before execution

A fresh-context independent model reads this protocol and the frozen source `experiment/revision/independent_gate_v3_controls.py` (SHA256 `35f9427837c97e0ae838eeb3348ca4b30d632bc8403a887186861b59cce7ab6e`). It assigns vc025, vc026, vc027 and vc028 one role, quoting source evidence:

- `direct_repair`: after the initial SQL is executed and fails, the next LLM request expects repair SQL. Classification can happen locally.
- `classify_then_repair`: after that failure, the next LLM request expects one classification category; the following LLM request expects repair SQL. Assignment concerns the requested response type even if the returned category is subsequently discarded.
- `ambiguous`: the source does not support a unique one of these finite sequences (including unsupported variable or multiple-classifier sequences).

The annotator must not read instrument implementation, old results, author labels, previous adjudication or new profile outputs. Role assignment does not adjudicate conformance. Save the map with source/protocol hashes before running profiles. These four controls are already exposed to the implementing team; this is development regression, not a new independent calibration sample.

## Finite responder and interpretation

Use observed API order, never prompt keywords, to select response roles: initial LLM -> execute failure -> first post-failure LLM. The `direct_repair` profile supplies repair SQL there; the `classify_then_repair` profile supplies the probe's single correct category there and repair SQL on the next call. Record delivered responses and state transitions. A successful initial execution receives no classification injection. Unsupported order is reported as interface review required, not silently mapped to a different profile.

Repair SQL delivery retains gate-v3's exact-feedback counterfactual rule. Existing initial execution, single-sample, success-path and feedback requirements still apply; all classification mechanisms require independent action-semantic review. Returning a correct final SQL is not sufficient for admission. This component produces observations and never automatically admits a control.

Each case is run on the same seven gate-v3 error_classify probes, salt `independent-v3-20260910`, using both profiles. The source-assigned profile is primary; the other is explicitly diagnostic and never substitutes for it. An ambiguous assignment has no primary result and remains review_required, regardless of diagnostic outputs. No profile selection after results.

For the two classifier-role controls, additionally deliver `UNRECOGNIZED_CATEGORY` and `syntax or schema` on the first post-failure classification call. These are diagnostic tests only. No conformance/admission rule is inferred from their behavior in this stage.

Correct category injection tests whether a category response is consumed and drives the appropriate downstream action. It does not measure actual model classification accuracy. Independent action review uses source and complete primary traces; source/reference disputes from earlier measurements remain disputes. All primary controls retain review_required at the component level until independently adjudicated. Diagnostic structural flags cannot override primary results or create conformance labels.

## Bounded completion

Deliver source-only mapping, versioned responder and regression tests, complete primary/diagnostic traces, independent review of primary actions, and a short report of what changed and what remains unresolved. Keep gate-v3 and frozen controls byte-identical. No new full calibration batch and no production gate integration are part of this stage.
