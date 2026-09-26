# V8: improve what the teaser explains, using v6 as the reference

The user rejected the v7 rearrangements. This round keeps v6's 396 × 198 pt footprint, three scientific questions, typography, and all six evidence groups. The alternatives explore different scientific explanations. V6 is preserved byte for byte and appears first in `comparison_with_v6.pdf`.

| Option | Added perspective | Main tradeoff |
|---|---|---|
| A — calibrated comparison | Both arms visibly undergo the same held-out procedure; D is the generated gain minus the same-code gain. A small baseline/member score key explains persistent losses. | The most restrained revision. It adds interpretation while retaining v6's illustration and full statistical plots. |
| B — recorded outcomes | Eighteen program cards show all 54 recorded scores for one selected task. Identical code produces varying outcomes; several generated members repeat a scored failure. | The outcomes are concrete but small at manuscript size. The selected example needs explanation and has less visual warmth than the original illustration. |
| C — task-wise crossover | Two conceptual success-probability sketches distinguish dominance from crossover. Stable headroom requires the better member to change across tasks. | The strongest addition to the conceptual story, but the method moves into the right result panel and its interval display is more compact. |

No new option is automatically adopted. A is the conservative refinement to consider first; C is the more substantive conceptual alternative. B remains an empirical exploration. These are figure-design judgments, not independent scientific peer review; neither A nor C is claimed to be categorically better than v6.

## Self-review and revisions

The first A draft used similarly sized loss and win cards. Review found that this weakened the immediately visible 100-to-1 contrast. Final A restores the one-square-per-task grid and keeps a small score key. Its glyph separator denotes comparison, not execution order.

The first B draft used 2.1 pt circles with thick outlines. Wrong/correct markers were difficult to distinguish. Final markers are 2.8 pt across with a 0.35 pt outline, and the task is explicitly labeled **Selected example #138**. The example still imposes a reading cost at native size; it is not recommended over A as the main teaser.

C originally labeled the concept “stable gain.” This became **stable headroom**, distinguishing the population quantity from measured held-out gain G. The sketches are explicitly schematic and identify p as success probability. Its empirical interval remains linear in pp, with labeled endpoints and a zero reference.

## Evidence and interpretation

Every candidate preserves:

1. All nine execution-matched oracle-replay budgets and the observed 98.70% tie at 27 executions.
2. Repeat-mean estimated headroom of 2.33 pp generated and 2.16 pp same-code.
3. Residual score-pattern correlations 0.789 and 0.006, with their 95% intervals.
4. One hundred persistent-loss tasks and one extraction-sensitive persistent-win task.
5. Clone-adjusted held-out gain −0.26 pp, 95% CI [−1.45, +0.95] pp; specialization remains unresolved.
6. The frozen feature selector's baseline choice on all 386 tasks and 0.00 pp gain.

The numerical source remains `artifacts/common386_20260926/analysis.json`. The repeat tensors are also checksum-bound. The full tensors reproduce 100 loss tasks, one win task, 570 loss member–task pairs, and eight win pairs. Only task counts appear in the teaser. The condition is **at least one generated member** contrasting with baseline in **all three repeats**; it does not imply every member has that outcome. The sole persistent-win task is `math500_split#379` and is extraction-sensitive.

B's example is `math500_split#138`. Baseline scores are 111; the generated members in stored order have 000, 000, 000, 101, 010, 000, 000, 000. Clone-slot scores are 101, 111, 111, 101, 111, 110, 011, 011, 010. Each triplet is R1–R3. The first dark card in the generated arm is baseline. This case was chosen after inspecting outcomes; it is neither random nor representative and does not compute the population residual correlation. Program motifs are schematic, not reconstructed control flow.

C illustrates the manuscript's two-member population criterion:

`H_stable = E_task[max_member p(member, task)] − max_member E_task[p(member, task)]`.

With a uniformly better member, both terms choose it and headroom is zero. For two task types with positive probability and a genuine crossover, choosing per task improves on either fixed member. The drawn heights are conceptual population probabilities, not estimates from the study. This criterion does not establish that the generated panel exhibits crossover, nor does D directly estimate H_stable.

The D diagram uses held-out gains from the same evaluation procedure in both arms. It **does not subtract the headroom bars**. Individual rounded G values are omitted: rounding +0.095 pp to +0.10 and +0.354 pp to +0.35 would make the displayed subtraction appear to give −0.25 even though the unrounded difference correctly rounds to −0.26.

Repeat transfer on the same tasks and the frozen question-feature selector remain distinct. Oracle coverage uses post-execution correctness and matches harness executions, not tokens or model calls. The observed tie is not an equivalence result; the interval does not demonstrate absence of specialization.

## Physical format and checks

| Property | V6 | A | B | C |
|---|---:|---:|---:|---:|
| Native width × height | 396 × 198 pt | 396 × 198 pt | 396 × 198 pt | 396 × 198 pt |
| Minimum type | 7.5 pt | 7.5 pt | 7.5 pt | 7.5 pt |
| Visible words including ticks | 120 | 121 | 129 | 131 |
| Embedded bitmap illustrations | 1 | 1 | 0 | 1 |
| Principal evidence groups | 6 | 6 | 6 | 6 |

Raw PDFs have no overall title and embed STIX General. A and C reuse the original whole, unmodified illustration; charts, new explanations, and text are vector. B is entirely vector. SVGs preserve editable text but depend on the corresponding fonts. PNG files are previews only.

Checks cover native dimensions, embedded fonts and minimum size, text boundaries and normalized span overlaps, numerical labels, SVG validity, tensor hashes, and displayed example identities. Color, grayscale, and manuscript-size renders were reviewed. All 108 v1–v7 output files remain unchanged. These checks are not publisher-compliance certification.

`paper_fit_all.pdf` places each candidate at 100% manuscript width with a separate caption. It composes excerpts from the unchanged local manuscript PDF snapshot `922c914`; it is not a compilation of the current manuscript. No LaTeX files are edited.

V6 [PR #2](https://github.com/StatXzy7/AI4AI-Harness/pull/2) merged into main on 26 September 2026 at 10:22:24 UTC. V8 is developed separately on `jzsawyer-dev/teaser-v8`.

Rebuild from the repository root:

```bash
/home/batchcom/.conda/envs/ai4ai-teaser/bin/python -s paper/teaser/build_v8.py
/home/batchcom/.conda/envs/ai4ai-teaser/bin/python -s paper/teaser/preview_v8.py
```

The existing scientific-visualization workflow, accepted-paper reference survey, and skill attribution remain in the teaser README and earlier design notes.
