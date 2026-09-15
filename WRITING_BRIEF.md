# Writing brief: AI4AI-Harness (2026-09-15)

## Working state

- Checkout: `E:\projects\AI4AI-Harness`
- Base: local `main` at `9ffc70d` (`chore: update experiment run records and docs for 2026-09-12 sync`).
- Remote observed: `origin/main` points to the same branch tip at inspection time.
- The working tree already contained user changes in the original English and Chinese discussion sources, generated PDFs/logs, and live or partial acquisition artifacts. The revision is isolated and does not reset, clean, or overwrite them.
- Parallel-domain revision: `paper/latex/main_revision_20260915.tex`; insight-focused revision: `paper/latex/main_revision_20260915_insight.tex`.

## Evidence and policy sources

- Scientific evidence was traced through the current LaTeX source, `paper/latex/revision_numbers.tex`, the shared table fragments, `artifacts/revision_20260910/corrected_analysis.json`, `artifacts/revision_20260910/fingerprint.json`, `artifacts/phase2/completeness_report.json`, `artifacts/phase2/r3_flip_rate.json`, `artifacts/gsm8k_audit/metrics.json`, and the dated review-stage provenance records.
- ICLR 2027 Author Guidelines were checked on 2026-09-14: double-blind anonymity, main text at most nine pages, abstract deadline Sep 18, full paper deadline Sep 25, references excluded from the page limit, appendices allowed, and a mandatory AI-use statement outside the page limit. Source: https://iclr.cc/Conferences/2027/AuthorGuidelines
- ICLR 2027 AI Policy for Authors was checked on 2026-09-14: disclose required LLM use in the paper and submission form; authors remain responsible for content. Source: https://iclr.cc/Conferences/2027/AIPolicyForAuthors
- The reference study was checked at https://arxiv.org/abs/2608.08975 and its public code at https://github.com/MingLiiii/Dissecting_AI_Reviews. It motivates controlled rhetoric and separate writing/review workflows; its data are not evidence for this paper.

## Evidence-supported narrative

The reader should correct the inference that source or one-run outcome diversity is sufficient evidence for reproducible additional harness capability. The paper measures four distinct objects: source diversity, executed mechanisms, one-run outcome diversity, and repeat-stable or selectable value. The archived BIRD evidence establishes measurement boundaries and exposes why a clone control, cost matching, independent repeats, and frozen selection evaluation are required. It does not identify stable complementarity.

Selected main line: measurement audit (line B in the project prompt), with a negative or unresolved confirmatory conclusion. Phase I is discovery; Phase II is a post-review reanalysis of an archived factorial study; the MATH-500 item is a one-seed mini-audit; provider acquisition records are provenance only.

## Title candidates

1. **Auditing AI-Generated Harness Populations: Separating One-Run Diversity from Stable Complementarity** — selected; accurately names the audit and the unresolved boundary.
2. **From One-Run Diversity to Stable Complementarity in AI-Generated Harness Populations** — usable but less explicit that stable complementarity was not established.
3. **When Harness Diversity Is Not Yet Capability** — concise but too broad for the current single-target evidence.

## Contributions and evidence map

1. **Measurement separation.** Define source, trace, outcome, one-run headroom, stable headroom, and realized selection value, with a non-monotonicity counterexample. Supported by C-01/C-02 in `CLAIM_LEDGER.json` and the Phase-I trace audit.
2. **Auditable admission analysis.** Make the archived gate's structural exclusion of two allowed prompt strategies explicit and report the corrected factorial estimands. Supported by C-03/C-04 and the gate/extraction artifacts.
3. **Evidence boundary for routing claims.** Show outcome instability and the same-code artificial-headroom diagnostic; keep selection and cross-domain results descriptive. Supported by C-05/C-06/C-07.

## Section plan

- Abstract: problem, BIRD setting, strongest corrected results, explicit gate limitation, and unresolved stable-capability boundary.
- Introduction: deployment decision, measurement confusions, study stages, three contributions.
- Related work: population outcome structure and behavior-aware admission as adjacent but distinct questions.
- Phase I: discovery taxonomy and task-side headroom.
- Phase II design: factors, actual gate, raw-attempt cap, unequal realized cost, split, judge, and estimands.
- Results: corrected primary contrast; factorial and fixed-K sensitivity; execution variability and same-code diagnostic; exploratory selection boundary.
- Discussion/conclusion: what the evidence changes in evaluation practice and the minimum controls needed for a stronger claim.
- Appendix: provenance, cross-domain mini-audit, model inventory, worked traces, gate-control limitations, W1/W3 and cost details.

## Abstract checks

The insight-focused abstract is 193 words by the validation count, within the 180--230 working target. A neutral semantic counterpart is recorded in `REVISION_AUDIT.md`; it preserves the same facts, estimands, and limits.

## Submission assessment

The isolated English source is intended to compile with a nine-page main text and a supplementary appendix. It is not submission-ready as a scientific claim package: stable complementarity, a cost-matched real-versus-clone control, independent gate calibration, a controlled old/new bridge, and independent selector utility remain unresolved. Final author verification of the AI-use statement and submission metadata is also required.



## 2026-09-15 insight revision

The latest isolated draft makes the reviewer-facing insight explicit: population utility is a stable task--harness interaction problem, not a diversity statistic. It adds residual-error coverage as a falsifiable selection principle and labels it as a design hypothesis because the current archive does not compare residual-coverage selection with top-accuracy, random, or diversity selection on independent held-out tasks. MATH-500 remains parallel main-text evidence, not pooled with BIRD and not treated as a positive selector result.

Validation: `main_revision_20260915_insight.pdf` has 19 total pages, with the discussion/conclusion ending on page 9 before the AI-use statement; abstract count is 193 words; final LaTeX log has zero undefined references/citations, zero overfull boxes, and only underfull layout warnings.
