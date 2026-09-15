# Revision audit (2026-09-15)

## Scope and baseline

The isolated revision is based on local `main` at `9ffc70d`. No checkout, pull, reset, experiment launch, provider call, data rewrite, or push was performed. The original working tree contained pre-existing user edits and generated artifacts; those remain untouched.

## Selected narrative

The selected line is: **one-run source or outcome diversity is a measurement signal, not evidence by itself of reproducible additional capability**. The revised manuscript makes the archived BIRD reanalysis the central result, uses Phase I as discovery evidence, and labels MATH-500 and provider records by their actual scope.

## Abstract semantic check

The revised abstract states the same facts in direct form. Neutral counterpart for comparison:

> Automatically generated harnesses can differ in source code, execution traces, and correctness outcomes. We study how to interpret these differences on BIRD text-to-SQL with a discovery audit and a post-review reanalysis of an archived factorial study. The discovery audit found outcome-identical pairs and trace-level cases in which declared mechanisms were absent, untriggered, or broken. In the archived factorial study, free ungated generation had 8.56 percentage points of bare-inclusive one-run oracle headroom. The forced-and-gated versus free-and-ungated headroom contrast was -0.16 percentage points (95% CI [-0.83,+0.87]), and the implemented gate excludes two allowed prompt-level strategies. Repeated executions of the same code also produced apparent one-run headroom. These results separate source diversity, executed mechanisms, one-run outcome diversity, stable complementarity, and realized selection utility. They support reporting absolute oracle accuracy, best-fixed accuracy, admission policy, cost, and repeat variability together. They do not establish stable complementarity or a deployable selector. A cost-matched clone control, independent repeats, and frozen held-out selection evaluation remain necessary for that claim.

Both versions preserve the same estimand, primary values, gate exclusion, repeat diagnostic, and unresolved stable-complementarity limit.

## Main changes

| Area | Before | Revision | Scientific status |
|---|---|---|---|
| Title | `From One-Run Diversity to Stable Complementarity in AI-Generated Harness Populations` | `Auditing AI-Generated Harness Populations: Separating One-Run Diversity from Stable Complementarity` | Pure narrative sharpening; stable complementarity remains unresolved. |
| Primary result | Archived gate contrast described across current source | Keeps -0.16 pp, CI [-0.83,+0.87], p=0.647 and explicitly calls it a combined screening/conformance contrast | No fact change. |
| Headroom | Reported alongside outcome metrics | Keeps oracle, best-fixed, and headroom separate; rejects monotonicity and selector interpretations | Scope correction. |
| Repeat evidence | Existing R2/R3 discussion | Separates flip rates from treatment uncertainty and includes same-code 6.50 pp diagnostic | Scope correction; no new experiment. |
| W1/W3 | Exploratory values | Keeps oracle +0.35 pp, best-fixed -0.42 pp, headroom +0.78 pp and labels them descriptive | Scope correction. |
| Provider records | Current dirty discussion contained the same paragraph twice | Isolated revision retains the provenance exclusion once | Editorial correction only. |
| MATH-500 | Supplementary mini-audit | Retains 35 harness/400 eval one-seed result and explicit no-clone/no-factorial limits | No fact change. |

## Claim checks

- Every core numerical sentence in the isolated source is traceable to `CLAIM_LEDGER.json` or an existing macro/table fragment.
- The ledger distinguishes `reproduced`, `source-verified`, and `unresolved`; reading a JSON artifact is not marked as a rerun.
- Claims about stable complementarity, causal gate effect, deployable routing, and provider common-pool performance are excluded or marked unresolved.
- The revision does not turn finite gate-control checks into population error rates or independent scientific validation.

## Reader-understanding track

No independent model or paid reader study was run. The available check is a sequential, non-independent self-audit against the prompt's questions: research question = what evidence distinguishes one-run diversity from stable capability; contributions = measurement separation, explicit archived admission analysis, and the evidence boundary for routing; unproven = stable complementarity and deployment utility; main limitation = no balanced cost-matched real-versus-clone control. This is recorded as non-independent and is not a paper result.

## Commands and expected results

1. `python -m json.tool CLAIM_LEDGER.json` -> valid UTF-8 JSON.
2. `python -c "from pathlib import Path; p=Path('paper/latex/main_revision_20260914.tex'); print(sum(len(x.split()) for x in p.read_text(encoding='utf-8').splitlines() if '\\begin{abstract}' in x))"` -> source readable; abstract count checked separately below.
3. `python -m experiment.revision.verify` -> existing canonical source/analysis consistency gate; expected PASS within its recorded scope.
4. `latexmk -pdf -interaction=nonstopmode -halt-on-error main_revision_20260914.tex` from `paper/latex` -> exit 0, no undefined references, no overfull boxes, PDF emitted.
5. `pdfinfo paper/latex/main_revision_20260914.pdf` -> main text checked against ICLR's nine-page limit using the `endofmain` page marker; appendix pages are supplementary.
6. `pdftotext paper/latex/main_revision_20260914.pdf -` plus `rg` -> title, abstract, key values, and appendix text present.

## Final decision

The manuscript mechanics can be made ready within the checked source/PDF scope. The scientific submission package remains **not ready** for a claim of stable complementarity or deployable selection because C-09 is unresolved; this is a claim-scope verdict, not a LaTeX failure.

## Observed validation results

- `python -m json.tool CLAIM_LEDGER.json`: PASS; 9 unique claims, with 2 `reproduced`, 6 `source-verified`, and 1 `unresolved`.
- `python -m pytest experiment/revision -q`: **141 passed, 45 subtests passed** in 51.14 seconds. These are project revision/instrument tests and do not close the scientific evidence gaps.
- `latexmk -pdf -interaction=nonstopmode -halt-on-error main_revision_20260914.tex`: exit 0 after BibTeX and three LaTeX passes; emitted 19-page PDF.
- Final log scan: no undefined references, undefined citations, or overfull boxes. Underfull boxes remain in a few long table/code lines.
- `pdfinfo`: 19 total pages; the `endofmain` marker is on page 9, so the ICLR main-text limit is satisfied in this build.
- `pdftotext` key-value check: PASS; title, primary values, same-code diagnostic, MATH-500 scope, and stable-complementarity boundary are present.
- Visual inspection: rendered pages 1, 9, 10, and 19; title/abstract, main-text boundary, appendix transition, tables, and cross-domain appendix were readable without clipping or blank-page artifacts.
- `python -m experiment.revision.verify`: **STALE** against the current original checkout because its recorded hashes are for `main.tex` and the existing source set. This is preserved as an evidence status; the isolated revision was checked by its own build/log/text validation.

Build artifact SHA-256: `a654ddcea7aa3a3cdc2c38e539dabfa7e851a4ad738e7c435ae6d9899036f7df`.
Source SHA-256: `b382c032ece5bc39ae9c805c2de17fadc2650d9432729e5fdb9ee5f4b57aa164`.


## 2026-09-15 insight revision

The reviewer-facing narrative was sharpened without inventing a positive result. The manuscript now states the central insight as a measurement principle: population utility requires stable, task-conditional task--harness interaction after execution noise is separated. It also states residual-error coverage as a falsifiable selection principle. The text explicitly says that the current BIRD and MATH-500 evidence motivates this principle but does not test it as an intervention.

The MATH-500 probe remains in the main result table alongside BIRD, with no pooling: 35 harnesses, 400 evaluation tasks, 10.6% disagreement, 98.50% oracle, 93.75% bare best-fixed, and 4.75 pp observed headroom. Its one-seed/no-repeat scope is repeated in the abstract, results, discussion, and appendix.

Observed validation for `paper/latex/main_revision_20260915_insight.tex`: `latexmk -pdf -interaction=nonstopmode -halt-on-error` exit 0; 19-page PDF; main text ends on page 9 before the AI-use statement; abstract 193 words; final log has 0 undefined references, 0 undefined citations, 0 overfull boxes, and 16 underfull warnings. Visual inspection of pages 1, 9, and 10 found no clipping.

Scientific verdict remains **not ready** for a claim of positive stable complementarity or deployable residual-coverage selection: the required same-candidate-pool held-out selection experiment is still absent.
