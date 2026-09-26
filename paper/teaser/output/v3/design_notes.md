# V3: a compact evidence narrative

The feedback on v2 was excessive blank space, unattractive typography, and too little scientific information. V3 replaces large standalone numbers with an experimental diagram and measured plots. There is no global title. Both variants carry the same evidence; their setup illustration differs.

- **Academic:** vector program glyphs, protocol, plots, symbols, and embedded text. Recommended when editability and small-size clarity are priorities.
- **Illustrated:** the original unmodified conceptual artwork replaces only the program glyphs. All labels and quantitative content remain vector. The PDF contains one bitmap; the PDF container does not make that bitmap vector.

Both pages are 396 × 269 points (5.5 × 3.74 inches). Source Sans 3 replaces DejaVu; headings are 8.6 pt, most labels 6.3–7.5 pt, and the largest number 10.5 pt. The minimum text size is 6.1 pt, including the equation subscripts and small plot ticks. The design should be inserted at its native width rather than shrunk into a single narrow column. An author-approved caption should accompany it later.

## What the graphics now communicate

| Panel | Visual encoding | Scientific meaning |
|---|---|---|
| a | Eight different program glyphs plus a baseline, compared with nine identical-code slots | The control preserves repeated attempts while removing program variation. Glyphs are schematic, not traces. |
| b | Three repeat columns and three rotations, with dark cells explicitly labeled “test” | Freeze the per-task member choices and best fixed member on two discovery repeats; score their difference on the held-out repeat. Compare the gains between arms. |
| c | All nine observed budget points; solid/circle versus dashed/square encoding | Execution-matched post-execution oracle coverage converges to an observed 98.70% tie at 27 harness executions. The paired zero-origin bars below are the distinct repeat-mean oracle-headroom statistic. |
| d | Residual-correlation confidence intervals, followed by a unit-square tally | Program-dependent score patterns repeat, but persistent losses dominate persistent wins against baseline. Each square is one task; counts refer to any member showing the difference in all three repeats. |
| e | Clone-adjusted held-out interval crossing zero; separate frozen-policy outcome | Complementarity remains unresolved. The tested feature selector chooses the baseline on all 386 tasks and gains 0.00 pp against it. |

The replay controls harness executions, not token or model-call cost. Clone replay uses exact uniform-subset averaging. A persistent loss task does not imply that every generated program fails there. The one persistent scored win is extraction-sensitive. The held-out same-task repeat diagnostic and the practical question-feature selector are separate procedures. Neither the coverage tie nor an interval crossing zero establishes population equivalence.

## Accepted ICLR papers inspected

These are design observations, not claims that ICLR prescribes this layout. No figure artwork or numerical content was copied.

1. **ReAct, ICLR 2023, Figure 1 (PDF p. 2).** The aligned examples carry evidence within the comparison, with short local labels and meaningful color. Applied here: aligned controls and evidence plots instead of detached headline metrics. [Accepted-version PDF](https://arxiv.org/pdf/2210.03629#page=2).
2. **Automated Design of Agentic Systems, ICLR 2025, Figure 1 (PDF p. 2).** The overview links a compact process to nested examples of program structure. Applied here: the control-program diagram and an explicit repeat-validation protocol occupy the top band. [Official proceedings PDF](https://proceedings.iclr.cc/paper_files/paper/2025/file/36b7acf6f6010652b3f2a433774a66fe-Paper-Conference.pdf#page=2).
3. **Scaling LLM Test-Time Compute Optimally Can Be More Effective than Scaling Parameters for Reasoning, ICLR 2025, Figure 1 (PDF p. 2).** A small-multiple result figure carries multiple comparisons through actual curves and quantitative labels. Applied here: retain the full budget curve and the uncertainty intervals, using compact common typography. [Official proceedings PDF](https://proceedings.iclr.cc/paper_files/paper/2025/file/1b623663fd9b874366f3ce019fdfdd44-Paper-Conference.pdf#page=2).

DSPy ICLR 2024 was checked but excluded as a front-of-paper teaser reference: its first numbered figure is an appendix prompt example. The references above were inspected on 26 September 2026.

## Fonts, provenance, and checks

Source Sans 3 Regular, Semibold, and Italic were downloaded from [Adobe's official repository](https://github.com/adobe-fonts/source-sans/tree/release/TTF). The original files and SIL Open Font License are in `../../assets/fonts/`. Their checksums and download URLs are in `../../assets/fonts/provenance.json`.

Numerical data come exclusively from `artifacts/common386_20260926/analysis.json` at commit `922c914cc7ce218e43b5a7114e582cf35632d253`; the source checksum is recorded in `provenance.json`. Changes are unit conversion and display rounding, with no re-estimation or simulated results. The generator is `../../build_v3.py`.

Validation checks page dimensions, embedded fonts, text within page bounds, source-linked numbers, and the hashes of all 25 pre-existing v1/v2 files. The PDFs were also visually reviewed in color and grayscale. Grayscale inspection is a practical check, not a certification of accessibility. No LaTeX files were edited.
