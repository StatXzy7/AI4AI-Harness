# V5: one illustrated controlled comparison

V5 implements the approved proposal: make the same-code comparison the visual centerpiece, distinguish persistent scored differences from useful specialization, and keep uncertainty visible. It produces one illustrated version only. The earlier v1–v4 files remain unchanged.

The intended takeaway is **additional answers and repeatable differences do not by themselves establish useful specialization**. This sentence guides the composition; it is not added as a figure title.

## Composition

- **Left:** the original program artwork is enlarged from 100 to 178 pt wide. Eight generated programs plus a baseline are compared with nine identical baseline slots. Two zero-anchored bars share a scale and show repeat-mean estimated oracle headroom of 2.33 and 2.16 pp. The artwork is an unmodified conceptual illustration, not execution traces.
- **Middle:** exactly 100 triplet glyphs represent persistent-loss tasks, and one represents the extraction-sensitive winning task. Each glyph is one task; its three bars represent the requirement that the scored difference persist across all three repeats. At least one generated member must exhibit that difference against baseline. These counts are not a partition of all 386 tasks, and do not mean every program fails on those tasks.
- **Right:** two discovery repeats freeze the per-task member and the best fixed comparator, then a held-out repeat measures gain; the held-out repeat rotates. The clone-adjusted statistic is −0.26 pp with a 95% paired-task-bootstrap interval of [−1.45, +0.95] pp. The figure explicitly says “Specialization unresolved.” This tests another execution of the same tasks, not routing to unseen tasks.

The nine-budget coverage curve, residual-correlation plot, and frozen feature-policy block are omitted from this teaser to give the controlled comparison more space. Those results remain in the paper and in earlier figures. No numerical results have been changed or re-estimated.

## Paper dimensions and typography

| Property | V5 |
|---|---:|
| Native PDF width | 396 pt / 5.5 in |
| Native PDF height | 198 pt / 2.75 in |
| Width : height | 2 : 1 |
| Smallest text | 7.5 pt |
| Typical labels | 7.5–8 pt |
| Panel headings | 8.5 pt |
| Fonts | STIX General Regular / Bold |
| Global title | None |

The fonts are Times-compatible in appearance and are embedded in the PDF. They are not the exact Nimbus Roman font in the existing manuscript. The 7.5 pt minimum is larger than v4's 6.5 pt minimum without increasing the figure height. Teal/ochre identify the arms; marker shapes and hatching provide redundant encoding. Red indicates persistent losses and is also directly labeled.

The PDF contains one raster artwork and vector data marks, typography, and protocol shapes. Its SVG sibling keeps editable text and embeds the artwork; SVG font appearance depends on the installed fonts. PNGs are inspection previews, not the manuscript deliverable.

## Evidence and limits

The numerical source is `artifacts/common386_20260926/analysis.json`, frozen by SHA-256 in `provenance.json`. Values were checked against the newer manuscript at commit `782bacec0579a4e2ccfea956999235af74ce3bee`.

- Scope is the selected low-call panel, one solver, and 386 complete MATH-500 tasks; fourteen incomplete tasks were excluded.
- Estimated oracle headroom and held-out gain D are different estimators. D is not the subtraction of the two displayed headroom bars.
- The sole persistent win depends on asymmetric answer extraction; the figure marks it explicitly. The counts describe scored differences, not established differences in reasoning capability.
- Three repeats have limited sensitivity to task-wise crossovers. An interval crossing zero does not establish absence of specialization or equivalence.
- Equal slot and repeat counts do not establish equal token or model-call costs.

## Page proof and validation

`paper_fit_illustrated.pdf` is a separate PDF composition at the natural figure width, with a 10 pt caption and a manuscript text excerpt. Its source is the unchanged local `paper/latex/main.pdf` from commit `922c914cc7ce218e43b5a7114e582cf35632d253`, not a newly compiled version of the newer main branch. The proof is labeled accordingly; no LaTeX or manuscript PDF was changed.

`validation.json` records page dimensions, fonts, text boundaries, numerical-label checks, image count, and hashes. `paper_fit_validation.json` records caption geometry and the unchanged manuscript hash. `previous_versions_manifest.json` protects all archived v1–v4 outputs. Color and grayscale renderings were reviewed, including the figure at manuscript width; these checks are not a publisher-compliance certification.

Rebuild from the repository root using the existing environment:

```bash
/home/batchcom/.conda/envs/ai4ai-teaser/bin/python -s paper/teaser/build_v5.py
/home/batchcom/.conda/envs/ai4ai-teaser/bin/python -s paper/teaser/preview_v5.py
```

The established scientific-visualization workflow and its attribution are documented in `../../README.md`; accepted ICLR design references remain in `../v3/design_notes.md`.
