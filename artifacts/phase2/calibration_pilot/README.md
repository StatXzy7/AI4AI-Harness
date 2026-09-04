# Calibration pilot — EXCLUDED from all Phase-II confirmatory analysis

Everything in this directory was produced **before** the Phase-II generation protocol was
frozen, or under an arm-E contract-elicitation protocol that was subsequently retired. None of
it appears in any quantitative table, and none of these harnesses may be re-counted as an
admitted candidate.

## `smoke_{A,D,E}_deepseek.json`

Pipeline smoke tests run under the pre-freeze generator, which gave gated arms 3 retries and
ungated arms 1 — the budget asymmetry the frozen protocol removes. Superseded by the equal-budget
sweep in `../gen/`.

## `raw_E_deepseek_s0/` — the arm-E contract-elicitation pilot

Arm E admitted 0 of 4 slots: neutral validity 0.92, mechanism pass 0.00.

**This is not evidence that open-mechanism generation fails.** Diagnosis showed the
implementations were real and non-vacuous; the builder systematically **over-asserted** its own
behavioural contract. One candidate declared all seven DSL properties, including
`branches_on_execution`, while making four LLM calls and returning the same answer whether or
not the first query executed cleanly.

To establish that the gate was discriminating rather than simply strict, one contract was
**manually** reduced from seven properties to the five the implementation actually satisfies;
the harness then passed, and the reduced contract was still non-vacuous (bare violates four of
its properties). That manual reduction was a **gate-calibration measurement only**. It is not an
admission decision, and the candidate is not admitted: allowing the evaluator to narrow a
contract after reading the trace would be relabelling a mechanism after seeing how it behaved.

The pilot motivated the retired protocol being replaced by two-stage elicitation (free
generation, code frozen, then a minimal self-audit contract) with a three-layer gate. Arm E is
regenerated from seed 0 under that protocol; nothing here carries forward.
