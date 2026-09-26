# v2 design exploration

The user requested no title, less text, an academic appearance, and all versions inside the existing output folder. These are standalone PDFs; no manuscript integration has been performed.

## Two perspectives

**Academic — explain the control.** Put the two program populations in a small shared legend, then compare oracle headroom, score repeatability, and the frozen selector. The bottom line retains the clone-adjusted held-out gain and interval. This is the recommended manuscript option because it makes the evidential distinction explicit with very little prose.

**Illustrated — foreground the surprising result.** Use the original programs-versus-rolls artwork as a small comparison scene. Make the observed 98.70% oracle-coverage tie at 27 harness executions the main visual anchor, with repeatability and the frozen selector to its right. This is the more visual alternative and avoids making an experimental overview into the main subject of the teaser.

Both are new compositions, with no global title. Repeated arm labels and explanatory paragraphs have been removed. Color plus circle/square markers or direct arm labels distinguishes the populations. The artwork is unchanged from v1; every scientific label remains editable/searchable vector text.

## Size and text comparison

Word counts use PyMuPDF's extracted PDF words, including numbers and symbols. They are a reproducible count, not a linguistic word-count convention.

| Design | Visible words | Native width × height | Height reduction from v1 |
|---|---:|---|---:|
| v1 academic | 135 | 5.50 × 4.50 in | — |
| v2 academic | 59 | 5.50 × 2.58 in | 43% |
| v1 illustrated | 134 | 5.50 × 5.88 in | — |
| v2 illustrated | 47 | 5.50 × 2.47 in | 58% |

## Scientific details retained outside the figure

The source is the frozen common-complete-set analysis in `artifacts/common386_20260926/analysis.json`, with SHA-256 recorded in `provenance.json`. All quantities concern the same 386 MATH-500 tasks. The generated arm includes eight selected generated harnesses and the single-call baseline. The control has nine byte-identical baseline slots. Each member/slot has three repeats per task.

- **Oracle headroom:** the repeat-average plug-in oracle estimate, 2.33 pp for the generated panel and 2.16 pp for clones. This is post-execution descriptive headroom; the clone estimate is positive despite zero code specialization. Both designs explicitly identify the measure as repeat-averaged or repeat-mean to distinguish it from full-budget replay.
- **Repeatability:** residual score-pattern correlation after removing additive member/task effects. Values are 0.789 versus 0.006. The academic figure shows source-provided 95% bootstrap intervals, approximately [0.75, 0.83] and [−0.07, 0.08]. The illustrated figure shows only the point estimates, with the intervals documented here.
- **Direction of repeated differences:** persistent scored losses to baseline span 100 tasks; persistent wins occur on one task, and that win is sensitive to answer extraction. This is intentionally omitted from the small figure rather than presenting the one-win claim without its qualification.
- **Frozen selector:** the tested policy's final choices are baseline on all 386 tasks, yielding 0.00 pp against the development-selected fixed baseline. This is not a claim that all possible selectors fail.
- **Full-budget replay:** 98.70% is observed post-execution oracle coverage in both arms at 27 harness executions per task. The equality sign applies only to this observed quantity. It is not an equivalence test, deployed selector accuracy, or an equal-token-cost result. Harness execution counts are matched; model-call counts and token costs vary by program.
- **Held-out validation:** clone-adjusted gain is −0.26 pp, with a 95% interval of [−1.45, +0.95] pp. Stable complementarity remains unresolved. Neither figure changes that conclusion into "no specialization."

The two alternatives differ in emphasis, so not every statistic appears in both. Both retain the labels "oracle," "frozen selector," and "unresolved" to preserve the important boundaries with minimal wording.

## Files and checks

`teaser_academic.pdf` is fully vector. `teaser_illustrated.pdf` embeds one unmodified conceptual artwork image, with vector labels. The corresponding SVG files preserve editable text. PNG and grayscale files are inspection previews only. `teaser_both_styles.pdf` contains one alternative per page.

Automated checks inspect searchable numeric labels, page bounds, embedded fonts, and absence of a global title. Visual review checks label placement and grayscale distinctions. The v1 archive is checked against its original file hashes. These are rendering and design checks, not a new independent scientific validation of the experiment.
