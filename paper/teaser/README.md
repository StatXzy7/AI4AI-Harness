# Standalone teaser designs

Versioned standalone figures for **More Programs or More Rolls? Separating Coverage from Specialization in LLM Harnesses**. No LaTeX manuscript files are changed or integrated.

- **Latest: `output/v5/teaser_illustrated.pdf`.** One illustrated design: the same-code control and estimated headroom, persistent scored differences, and unresolved held-out gain. It keeps the 2:1 manuscript footprint, enlarges the original artwork, and raises the minimum label size to 7.5 pt. The page-size proof is `output/v5/paper_fit_illustrated.pdf`.
- `output/v5/design_notes.md` explains the scientific hierarchy and PDF production; `output/v5/captions.md` keeps the caption outside LaTeX. V5 has no academic alternative or combined-style export.
- `output/v4/teaser_academic.pdf` and `output/v4/teaser_illustrated.pdf`: preserved manuscript-sized 2:1 figures with the wider set of results. Both options remain in `output/v4/teaser_both_styles.pdf`; page-size placement proofs remain in `output/v4/paper_fit_both_styles.pdf`.
- `output/v4/design_notes.md` records dimensions, font sizes, the caption budget, and validation. Placement proofs are separate PDF compositions, not a revised or compiled manuscript.
- `output/v3/teaser_academic.pdf` and `output/v3/teaser_illustrated.pdf`: preserved denser designs with Source Sans 3 typography, the three-fold validation protocol, all nine replay budgets, residual-correlation intervals, the persistent loss/win tally, and held-out/feature-selector results.
- `output/v3/design_notes.md` records the design lessons from actual accepted ICLR figures and exact scientific distinctions; `output/v3/captions.md` provides an optional caption kept outside LaTeX.
- `output/v1/`: the approved first versions, archived byte for byte. `archive_manifest.json` records hashes of all nine original output files.
- `output/v2/teaser_academic.pdf`: preserved previous title-free academic design, entirely vector, with embedded fonts and searchable text.
- `output/v2/teaser_illustrated.pdf`: preserved previous illustrated design; the conceptual artwork is raster, while all measurements and typography are vector. A PDF container does not turn the artwork into vectors.
- `output/v2/teaser_both_styles.pdf`: both previous options in a two-page PDF.
- `output/v2/design_notes.md`: the two design perspectives, visible-word/size comparison, and scientific definitions moved out of the artwork.
- `output/v2/captions.md`: accompanying caption drafts for review, kept separate from the manuscript.
- The sibling SVGs preserve editable text. PNGs are inspection previews only.

V5 is the current illustrated proposal for the manuscript. Its program comparison uses the unmodified original bitmap, with vector plots, task glyphs, protocol diagram, and searchable embedded text. It is 5.5 × 2.75 inches, matching the repository's text width. The page-size proof demonstrates the width, caption, and body-text relationship using excerpts from the local manuscript snapshot; actual LaTeX float placement and pagination remain to be checked upon authorized insertion. V1–v4 outputs are preserved and hash-checked by the v5 build.

## Evidence

V5 was reviewed against manuscript commit `782bacec0579a4e2ccfea956999235af74ce3bee`. The unchanged numerical source and local page-proof PDF originate from commit `922c914cc7ce218e43b5a7114e582cf35632d253`. The proof is explicitly a composition of that older PDF, not a compilation of the newer manuscript.

Source: `artifacts/common386_20260926/analysis.json`. Its SHA-256 and output metadata are recorded in each version's `provenance.json`. Quantities are read directly from this file, with display rounding only. These are the complete-set MATH-500 repeat-study results, not the older BIRD-centered draft or the full 35-program single-run analysis.

The study compares eight generated programs plus the baseline with nine byte-identical baseline slots on 386 common tasks, with three repeats per slot. The main distinction is between oracle coverage, repeatable score patterns, and useful selection before execution. The selected feature policy gains 0.00 pp; this is a result for that policy and feature set, not a claim that every possible selector fails. The 98.70% tie is observed post-execution oracle coverage at 27 harness executions, not equal token or model-call cost. The held-out diagnostic remains unresolved, not equivalent to zero specialization.

Persistent loss/win task counts refer to at least one generated member exhibiting the scored pattern against baseline in all three repeats. The sole persistent win is extraction-sensitive. V5 shows the 95% paired-task-bootstrap interval for clone-adjusted held-out gain; earlier versions also show correlation intervals. Headroom and held-out gain are distinct estimators: the two headroom bars must not be subtracted to reconstruct D. Program diagrams and dice are conceptual artwork, not empirical traces or simulated data.

## Skill and tool survey

| Candidate | Best use here | Limitation and decision |
|---|---|---|
| [K-Dense scientific-visualization](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-visualization/SKILL.md) | Source-linked quantitative plots, editable PDF/SVG, export inspection | Applied its evidence, redundant encoding, native-size, and export guidance. Numerical content is rendered with Matplotlib. |
| [K-Dense scientific-schematics](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-schematics/SKILL.md) | Prompted scientific diagrams with a generation/review loop | Its documented output is raster PNG, with no vector export or DPI control. Surveyed; not executed. Packaging that PNG in PDF alone would not yield editable plots. |
| [Google Research PaperVizAgent, formerly PaperBanana](https://github.com/google-research/papervizagent) | Reference-guided planning, styling, and iterative critique of academic illustrations | A larger framework with API configuration and optional reference retrieval. Surveyed its original implementation; no full framework installation or agent pipeline was needed for these two figures. |
| Built-in `imagegen` skill | A vivid original metaphor for program variation and stochastic execution | Used once for the text-free conceptual artwork. Exact labels and results were added as vector PDF elements. The unmodified original and complete prompt are saved in `assets/`. |

Recommendation: pair scientific-visualization with imagegen for optional artwork. This gives precise, revisable scientific content while allowing a more expressive visual style. For a large series of reference-conditioned illustrations, evaluate PaperVizAgent separately.

Survey accessed 26 September 2026. These are workflow recommendations, not comparative benchmark results. K-Dense guidance was read from its primary source and a snapshot is saved under `research/`. No third-party skill CLI was executed.

The K-Dense skill materially informed the figure workflow; its requested attribution is recorded here: Timothy Kassis, Vinayak Agarwal, Yuhuan He, Darshil Patel, and Aubrey M. Brueckner (2026), *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*, [arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065). Author/year metadata were verified from arXiv. No manuscript bibliography was modified.

## Rebuild

Run `python -s paper/teaser/build_v5.py` from the repository root in an environment with Matplotlib, Pillow, and PyMuPDF. Then run `python -s paper/teaser/preview_v5.py` to compose the page-size proof. Both scripts write only `output/v5/`. They use bundled fonts and require no LaTeX installation, API credentials, or image-generation call. Previous generators are retained as `build_v1.py` through `build_v4.py`; do not run them unless intentionally rebuilding the archived outputs. The original source and README are also preserved in the v1 archive.

The dedicated Conda environment for this workspace is `/home/batchcom/.conda/envs/ai4ai-teaser`. Its plotting packages were installed from the existing local Conda cache. PyMuPDF 1.27.2 was repackaged from the existing local installation and installed into the new environment; the original environments were not changed. `environment.yml` specifies a conventional fresh setup, and `requirements.txt` records the direct library versions used for the final export.

The artwork was produced with the built-in image tool. `assets/illustration_prompt.txt` records its full prompt. Regenerating the exact bitmap is stochastic; rebuilding the PDFs uses the saved bitmap and frozen analysis.
