# V7: three illustrated alternatives for author choice

V7 explores layout and visual hierarchy while preserving every principal result group from v6. No candidate is automatically selected. V6 remains on `jzsawyer-dev/teaser` at commit `95b1054`; v7 is developed separately on `jzsawyer-dev/teaser-v7` so the v6 PR remains focused.

Start with **`comparison.pdf`**. It places all three raw figures at the same 396 pt width on one sheet. The option names and comparison title are outside the raw figures; none of the individual figures has a global title. `teasers_all.pdf` contains the three raw figure pages. `paper_fit_all.pdf` provides one manuscript-size proof per option.

## The choices

| Option | Composition | Strength | Tradeoff |
|---|---|---|---|
| A — refined columns | V6's shared study strip and three result columns; larger illustration, lighter protocol, shorter separators | Safest continuation of v6; most explicit fold diagram | Least change to the existing composition |
| B — evidence rows | Shared illustration above three horizontal rows; each question pairs its main and supporting result | Fast scanning; direct association of coverage/headroom, repeatability/losses, and held-out/feature selection | Coverage and interval plots are shallower; illustration has less visual dominance |
| C — illustrated board | Larger experiment illustration in the upper-left; coverage/headroom upper-right; repeatability and selection below | Strongest illustration and balanced allocation of space; protocol sits beside its corresponding result | Shorter interval axes and a compact fold icon that relies on adjacent explanatory text |

The design-review preference is **C**, with **B** a useful alternative for a reader who prioritizes a clear sequence of paired findings. **A** offers the most conservative refinement. These are visual judgments, not scientific acceptance of the manuscript.

## Constant information and physical size

Each candidate retains:

1. All nine execution-matched oracle-replay budgets and the observed 98.70% tie at 27 executions.
2. Repeat-mean estimated headroom of 2.33 pp for generated programs and 2.16 pp for identical-code controls.
3. Residual score-pattern correlations of 0.789 and 0.006, with their 95% intervals.
4. One hundred persistent-loss tasks and one extraction-sensitive persistent-win task, with the any-member/all-three-repeats qualification.
5. Clone-adjusted held-out gain of −0.26 pp with interval [−1.45, +0.95] pp, labeled unresolved.
6. The separate frozen feature selector's baseline choice on all 386 tasks and 0.00 pp gain.

The matched comparison is eight generated programs plus a baseline versus nine identical baseline slots, on 386 complete MATH-500 tasks with three repeats per slot. The repeat diagnostic freezes both per-task choices and the best fixed member on two repeats and tests the third, rotating the held-out repeat.

| Property | A | B | C |
|---|---:|---:|---:|
| Native dimensions | 396 × 198 pt | 396 × 198 pt | 396 × 198 pt |
| Width : height | 2 : 1 | 2 : 1 | 2 : 1 |
| Minimum text | 7.5 pt | 7.5 pt | 7.5 pt |
| Visible words, including ticks/numbers | 117 | 107 | 115 |
| Artwork display width | 146 pt | 142 pt | 168 pt |
| Principal evidence groups | 6 | 6 | 6 |

Fonts are embedded STIX General Regular/Bold, with a Times-like appearance. All plots, data glyphs, protocol shapes, and labels are vector content. Each raw PDF contains one unmodified original schematic bitmap. SVGs preserve editable text and embed the illustration, but rely on installed fonts for appearance. PNG files are inspection previews.

## Scientific interpretation

The source remains `artifacts/common386_20260926/analysis.json`, bound by checksum in the build. Values are displayed with rounding only; proportions are converted to percent/pp where needed. The underlying evidence was reviewed against manuscript commit `782bace`.

Oracle replay uses post-execution correctness and matches harness executions, not tokens or calls. Estimated headroom, residual correlation, and held-out gain are distinct quantities. The two headroom bars cannot be subtracted to recover D. The observed tie and inconclusive interval are not equivalence findings or proof that specialization is absent. The 100/1 task counts are not a partition of the cohort and do not imply that every generated member fails on all 100 tasks. The frozen feature-policy result concerns that policy, including fallback, rather than all possible routers.

## Checks and provenance

All candidates were inspected in color, grayscale, and manuscript-size previews. Automated checks cover dimensions, font embedding and minimum size, required source-linked numerical labels, full text boundaries, normalized text-span separation, and SVG syntax. All 83 archived v1–v6 output files remain hash-identical. These checks do not constitute publisher-compliance certification.

The page proofs use the unchanged local `main.pdf` snapshot `922c914`, a 52-word caption at 10 pt, and a vector body-text excerpt. Their labels explicitly identify them as PDF compositions, not LaTeX compilations. No manuscript file was changed.

Rebuild from the repository root:

```bash
/home/batchcom/.conda/envs/ai4ai-teaser/bin/python -s paper/teaser/build_v7.py
/home/batchcom/.conda/envs/ai4ai-teaser/bin/python -s paper/teaser/preview_v7.py
```

`build_v7.py --only A` (or B/C) is available for inspecting one candidate while developing; a full build is required to refresh the combined comparison and final provenance. The existing scientific-visualization workflow and attribution remain in `../../README.md`.
