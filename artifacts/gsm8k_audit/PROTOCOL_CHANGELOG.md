# GSM8K/MATH-500 Audit Protocol Changelog

## G1 (2026-09-09): domain description mismatch — full regeneration

**What happened.** The first generation round (6 builders x 8 slots, 2026-09-08
evening) told builders the domain was "grade-school math word problems (GSM8K)"
and described the solver's reply convention as "#### <number>" — a purely
numeric answer format. The neutral-validity smoke test also ran on GSM8K dev
questions. The evaluation set, however, was switched to MATH-500 earlier the
same evening (after GSM8K showed a ceiling effect: bare = 0.993), and ~30% of
MATH-500 gold answers are non-numeric LaTeX (fractions, intervals, tuples,
sqrt expressions). The mismatch was discovered during interim analysis:
several generated harnesses contained numeric-only answer parsers and were
provably unable to answer the LaTeX-gold tasks, independent of their math
quality (e.g. an ERNIE harness at 0.033 accuracy whose failure decomposed into
a broken verify-fallback plus numeric-only extraction).

**Decision.** All 42 first-round harnesses and their 7,600 collected eval rows
are quarantined as a pilot (`artifacts/gsm8k_audit/pilot_gsm8k_prompt/`,
`experiment/gsm8k/agents_pilot_gsm8k_prompt/`). Generation was rerun from
scratch with the corrected skeleton (MATH-500-style domain notes, LaTeX answer
formats listed, solve() returns a compact answer string) and smoke tests on
MATH-500 dev questions. The bare baseline was re-run under the corrected
answer-format instruction (0.9175 -> 0.938).

**Honesty note.** The pilot population remains informative as a robustness
observation (harnesses designed for one task format degrade catastrophically
when evaluated on another — 19 harnesses, mean pairwise disagreement 16.2%,
all below bare, two catastrophic), but it confounds task-format mismatch with
generation quality, so it is excluded from the primary audit. No pilot result
is reported as if pre-specified.

## G0 (2026-09-08): benchmark selection

GSM8K rejected after calibration (bare GLM-5.3-Flash = 0.993 on 150 eval
tasks; ceiling leaves no disagreement space). MATH-500 selected (bare = 0.9175
with the first prompt; judge validated 400/400 self-consistent).
