# V4: manuscript proportions and serif typography

The manuscript's local ICLR style sets `textwidth` to 5.5 inches and `textheight` to 9 inches. Its compiled body uses Nimbus Roman (Times-style text). The original Figure 1 appears at the top of page 2. These measurements come from `paper/latex/iclr2027_conference.sty`, `main.tex`, and the existing `main.pdf`; no venue-wide figure-size requirement is inferred.

| Property | V3 | V4 |
|---|---:|---:|
| Native width | 396 pt / 5.5 in | 396 pt / 5.5 in |
| Native height | 269 pt / 3.74 in | 198 pt / 2.75 in |
| Width : height | 1.47 : 1 | 2 : 1 |
| Share of 648 pt text height, figure only | 41.5% | 30.6% |
| Smallest text | 6.1 pt | 6.5 pt |
| Typography | Source Sans 3 | STIX General regular/bold |

V4 is 26.4% shorter. This comes from rearrangement rather than scaling down v3: the experiment becomes a 60 pt top band; the three evidence columns occupy the rest. All nine coverage budgets, both headroom values, residual correlations and their intervals, the 100:1 persistent-loss/win tally and caveat, the held-out interval, and the frozen-selector result remain. The full subtraction formula is left to the caption/notes rather than repeated in the top band.

STIX General supplies a Times-like serif texture that fits the manuscript better than the previous UI-style sans font. It is not the exact Nimbus Roman font embedded in the existing manuscript. Body labels are usually 7 pt, small annotations and ticks 6.5–6.8 pt, headings 8 pt, and emphasized values 8–9 pt. There is no global title. All fonts in the raw teaser PDFs are embedded.

## Files and placement proofs

- `teaser_academic.pdf`: entirely vector; preferred at manuscript width for the clearer program glyphs.
- `teaser_illustrated.pdf`: one unmodified conceptual bitmap in the setup band; all measurements and text remain vector.
- `teaser_both_styles.pdf`: the two raw figures for comparison.
- `paper_fit_academic.pdf`, `paper_fit_illustrated.pdf`, and `paper_fit_both_styles.pdf`: page-size proofs showing the figure at 100% width, a compact 10 pt caption, and a vector excerpt of the original manuscript text.

The placement proofs use a US-letter page, the actual 396 pt text width, and the original manuscript's running header. The figure occupies `(108, 82)` to `(504, 280)` PDF points. Caption plus chosen spacing brings the illustrated float footprint to about 287 pt, or 44% of the text height. This is a measured budget for the supplied proof, not a promise about LaTeX's float decisions or pagination.

The proofs are PDF compositions, explicitly labeled as such. They are not a compiled revision, do not reproduce every manuscript paragraph, and do not replace the existing paper. `paper_fit_validation.json` records the exact geometry and verifies the original manuscript PDF stayed unchanged. No `.tex` files were edited. Later author-approved integration should use the native text width and check actual float placement/page count.

## Evidence and validation

The numerical source and interpretation are unchanged from v3: `artifacts/common386_20260926/analysis.json`, frozen by checksum. Clone replay averages uniformly over subsets at matched harness execution counts. Persistent task counts require at least one generated member showing the scored difference against baseline in all three repeats; the sole persistent win is extraction-sensitive. Repeat-mean oracle headroom, post-execution coverage, held-out-repeat gain, and the frozen feature policy are distinct quantities. The held-out evidence remains unresolved.

The native PDFs were checked for embedded fonts, page boundaries, source-linked labels, grayscale readability, and visible collisions. The final page proof was reviewed at manuscript size. All 39 files from output/v1 through output/v3 remain hash-identical. Fonts and their original STIX license are bundled in `../../assets/fonts/`; font provenance is in `../../assets/fonts/stix_provenance.json`.

Rebuild from the repository root:

```sh
/home/batchcom/.conda/envs/ai4ai-teaser/bin/python -s paper/teaser/build_v4.py
/home/batchcom/.conda/envs/ai4ai-teaser/bin/python -s paper/teaser/preview_v4.py
```

The earlier accepted-paper design references and their observations remain in `../v3/design_notes.md`.
