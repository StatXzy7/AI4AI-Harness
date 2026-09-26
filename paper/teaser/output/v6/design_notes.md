# V6: restore the complete evidence at manuscript size

V6 restores the full quantitative backbone of v4 while retaining the larger minimum type size introduced in v5. The layout uses one shared illustrated experiment and validation strip above three result columns. Only the illustrated version is produced; all 71 archived v1–v5 output files remain hash-identical.

## Information retained

| Question | Main evidence | Supporting evidence |
|---|---|---|
| Coverage | All nine execution-matched oracle-replay budgets; both arms reach 98.70% at 27 executions | Repeat-mean estimated headroom: 2.33 pp generated, 2.16 pp same-code |
| Repeatability | Residual score-pattern correlations: 0.789 generated, 0.006 same-code; both 95% intervals | 100 persistent-loss tasks and one extraction-sensitive persistent-win task |
| Useful selection | Clone-adjusted held-out gain −0.26 pp; 95% CI [−1.45, +0.95] pp; specialization unresolved | Frozen feature selector chooses baseline on 386/386 tasks and gains 0.00 pp |

The three-fold diagram freezes both the task-wise choice and the best fixed member on two discovery repeats, then scores their difference on the held-out repeat. The separate frozen feature selector operates from question features before execution. The figure keeps those procedures distinct.

The coverage curve, residual-correlation plot, and practical selector block were absent from v5. All are restored, with no numerical re-estimation. Space comes from compact labels, a shared experiment strip, and a smaller task-count grid.

## Typography and proportions

| Property | V4 | V5 | V6 |
|---|---:|---:|---:|
| Native PDF dimensions | 396 × 198 pt | 396 × 198 pt | 396 × 198 pt |
| Width : height | 2 : 1 | 2 : 1 | 2 : 1 |
| Smallest type | 6.5 pt | 7.5 pt | 7.5 pt |
| Visible words, including plot ticks/numbers | 128 | 88 | 120 |
| Original artwork display width | 100 pt | 178 pt | 124 pt |
| Principal result groups | 6 | 3 | 6 |

There is no global title. STIX General Regular and Bold give a Times-like appearance and are embedded in the PDF. These are not the exact Nimbus Roman fonts used in the local manuscript. Regular labels are at least 7.5 pt, result-column headings are 8.5 pt, and key estimates are 8.5–10 pt. The illustration is 24% wider than v4. The color/shape legend is shared across panels; hatching and line styles preserve the arm mapping in grayscale.

The source artwork is displayed whole and unmodified. It is a schematic bitmap; all numerical plots, count glyphs, protocol cells, and text are vector content. The SVG retains editable text and embeds the image, but relies on installed fonts for text appearance. PNGs are inspection previews.

## Scientific scope

- All reported quantities use the 386-task complete MATH-500 cohort, the selected low-call panel, and one frozen solver. They do not describe the separate full 36-member single-run population or BIRD studies.
- Coverage is a post-execution oracle quantity. The budget matches harness executions, not calls or tokens. The observed full-budget tie is not an equivalence finding.
- Repeat-mean estimated headroom can be positive for identical programs. It is not population stable complementarity and does not determine the held-out statistic.
- Residual correlations describe scored-outcome patterns, including possible answer-format effects.
- The 100/1 task counts require at least one generated member to lose/win against baseline in all three repeats. Each square represents one task. They are not counts of programs, not a partition of the cohort, and do not mean all generated members lose on all 100 tasks. The sole win is extraction-sensitive.
- Held-out gain compares choices learned on earlier outcomes for the same tasks. Three repeats have limited power; the result remains unresolved. The feature-selector result concerns that one frozen policy and its fallback, not all possible routers.

Values come from `artifacts/common386_20260926/analysis.json`, checksum-bound in the generator and provenance. The source was reviewed against manuscript commit `782bacec0579a4e2ccfea956999235af74ce3bee`.

## Export and checks

The raw PDF is 5.5 × 2.75 inches. Numerical labels, page boundaries, embedded fonts, normalized text-span separation, SVG syntax, archive hashes, and color/grayscale renders were checked. Visual review covered the manuscript-size proof as well as the raw figure.

`paper_fit_illustrated.pdf` is a separate composition with the figure at natural width and a 52-word, 10 pt caption. The caption occupies about 50.55 pt; figure, caption, and chosen spacing occupy about 275.55 pt. The proof uses the unchanged local manuscript PDF from `922c914`, explicitly labeled as a layout proof rather than a LaTeX compilation. No manuscript files were changed.

Rebuild using the existing Conda environment:

```bash
/home/batchcom/.conda/envs/ai4ai-teaser/bin/python -s paper/teaser/build_v6.py
/home/batchcom/.conda/envs/ai4ai-teaser/bin/python -s paper/teaser/preview_v6.py
```

The scientific-visualization workflow and attribution remain in `../../README.md`; the accepted-ICLR figure references remain in `../v3/design_notes.md`.
