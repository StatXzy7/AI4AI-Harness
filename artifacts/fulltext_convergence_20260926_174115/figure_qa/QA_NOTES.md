# Appendix figure revision QA

All three figures were rendered by the existing `sim-genesis` Python environment
using matplotlib. No package was installed. The `cv` environment imported the
libraries but failed during Bezier numeric operations with Windows exception
`0xc06d007e`; the bundled Python did not contain matplotlib. These failed
environment checks did not modify any scientific input.

## Integrity and scope

- The result chart reads the frozen corrected-analysis JSON. All 18 paired
  cell contrasts, the original pooled unadjusted interval, and all four core
  arm means are retained. Multiplication by 100 only changes proportion units
  to percentage points; no statistic, bootstrap, or scoring procedure is run.
- The discovery scatter retains all 91 archived pair coordinates, at their
  stored four-decimal precision. Axis limits include every point. Published
  rho, mean disagreement, and identical-pair counts are retained as annotations
  without recalculating them. The old horizontal mean line was replaced by the
  explicit numerical annotation; no data marks were removed.
- The design diagram replaces the unsupported never-opened statement with the
  disclosed evaluation exposure, and separates development-only II-E from the
  four-arm comparison. The implemented B/D gate is described as structural
  screening plus mechanism conformance after common neutral validity.
- `figure_manifest.json` records frozen input hashes, source hash, output
  hashes, and zero excluded input rows. Rendering verified that inputs were
  unchanged. PDF/SVG/PNG files in the two figure directories are byte-identical.

## Automated gates and visual review

| Figure | Panel alignment | PDF glyph floor | PDF collisions | Visual inspection |
|---|---|---|---|---|
| Design | PASS, 3 equal-width panels | 8 pt, PASS | 0 fail / 0 warn | All three panels and complete layout checked |
| Results | PASS, 2 aligned panels | 8 pt, PASS | 0 fail / 0 warn | Cell labels, zero reference, interval band and all arm bars checked |
| Discovery | NOT APPLICABLE, single panel | 8 pt, PASS | 0 fail / 0 warn | All points within bounds; annotation and axis clearance checked |

The source preflight reports 18 PASS, 3 WARN, and 0 FAIL. Warnings reviewed:

1. PNG rather than TIFF is intentional: the manuscript consumes vector PDF;
   PNG is the 600 dpi review preview, not a substitute submission raster.
2. The physical widths are chosen for the existing ICLR manuscript rather than
   Nature's default widths. Final placement uses 95 percent of the line width
   for the design/results figures and 75 percent for the discovery figure.
   The final English and Chinese PDFs were checked after embedding: sampled
   small labels measure 6.045--6.532 pt, including the discovery annotation,
   the development-only label, the smoke-test exception, and the result legend.
   All manuscript pages were rendered and inspected; the design and result
   pages were also inspected at full size. Final measurements are recorded in
   ../validation.json. Source-figure font sizes alone do not validate scaling.
3. The right result panel retains descriptive arm means with no newly invented
   uncertainty. The left panel preserves its frozen pooled 95 percent interval
   as a band, explicitly labelled. These panels have different evidence roles.

The collision audit's 34 contained-fill overlays in the design are intentional
labels centered inside their boxes. No partial-edge overlap is reported.

## Panel roles

- Design a: populations and disclosed development exposure; no uncertainty
  applies to protocol counts.
- Design b: the crossed four-arm design and paired-cell unit; no outcome data.
- Design c: neutral validity, the implemented gated bundle, and the separate
  development-only arm; no outcome data.
- Results a: heterogeneity of the 18 builder-seed contrasts, with the frozen
  pooled interval. Results b: descriptive headroom means on the shared core.
- Discovery: recorded source similarity versus correctness disagreement on
  60 tasks; pair observations are not interpreted as independent trials or
  as a test of program equivalence.
