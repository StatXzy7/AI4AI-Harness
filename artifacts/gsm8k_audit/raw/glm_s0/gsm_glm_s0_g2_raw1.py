"""Replaces single greedy decoding with a temperature-ladder self-consistency ensemble that votes on normalized '#### <answer>' strings, adjudicates close votes with a focused verification duel, and falls back to a format-repair call when nothing parses."""

from __future__ import annotations

import re
from fractions import Fraction

from ..harness_base import MathHarness


def _as_text(out) -> str:
    """Coerce whatever ``self.llm`` returns (str, list, dict, ...) into plain text."""
    if out is None:
        return ""
    if isinstance(out, str):
        return out
    if isinstance(out, (list, tuple)):
        return _as_text(out[0]) if len(out) else ""
    if isinstance(out, dict):
        for k in ("text", "content", "completion", "output", "response", "answer"):
            if k in out:
                return _as_text(out[k])
        return str(out)
    return str(out)


class GsmGsmGlmS0G2(MathHarness):
    """Consensus-plus-adjudication wrapper around the frozen solver.

    Control flow per problem:
      1. Greedy anchor solve (temperature 0).
      2. Up to N_SAMPLES sampled solves on paraphrased prompts across a
         temperature ladder (0.6/0.7/0.8/0.9), with an early exit once the
         greedy answer has been independently confirmed twice.
      3. All '#### <answer>' lines are extracted, cleaned, canonicalized and
         tallied; ties favor the greedy answer, then first occurrence.
      4. If the vote leader does not lead the runner-up by DUEL_MARGIN votes,
         a verification "duel" re-solves the problem with both candidates in
         view and picks the verdict.
      5. If no response contained a parseable marker at all, a repair call
         asks the solver to restate its final answer in the required format.
    """

    # ---- tunables ---------------------------------------------------------
    N_SAMPLES = 4                               # ensemble members beyond the greedy anchor
    SAMPLE_TEMPERATURES = (0.6, 0.7, 0.8, 0.9)  # diversity ladder for the samples
    EARLY_CONFIRMATIONS = 2                     # confirmations of greedy needed to stop sampling
    DUEL_MARGIN = 2                             # vote lead required to skip the duel
    REPAIR_CHAR_LIMIT = 2000                    # max raw chars fed into the repair prompt

    _SYSTEM = (
        "You are an expert competition mathematician. Solve the problem rigorously and "
        "always end your reply with the final answer on the last line in the exact form "
        "'#### <answer>'."
    )

    _PROMPTS = (
        # [0] greedy anchor prompt
        "Solve the following competition math problem.\n\n"
        "Reason step by step, then put your final answer on the last line in the exact form:\n"
        "#### <answer>\n"
        "The answer may be a plain number, a fraction, a LaTeX expression, an interval, or a tuple.\n\n"
        "Problem:\n{q}",
        # [1..4] paraphrased ensemble prompts (used by the sampled calls)
        "Work through the math problem below carefully. After you reach a solution, verify it with a "
        "quick independent check (substitute back, estimate, or try a second method). End your response "
        "with the final answer alone on the last line as:\n#### <answer>\n\nProblem:\n{q}",
        "Here is a competition math question. Write a clean, concise solution and check your arithmetic "
        "as you go. The very last line of your reply must be exactly:\n#### <answer>\n\nQuestion:\n{q}",
        "Please answer this math problem. Think it through slowly, then state the result. Finish with a "
        "last line containing only the final answer in the form:\n#### <answer>\n\nProblem:\n{q}",
        "Solve this problem from a math competition. Watch for sign errors and arithmetic slips before "
        "you commit to an answer. Conclude with the final answer on its own last line, formatted as:\n"
        "#### <answer>\n\nProblem:\n{q}",
    )

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        q = (question or "").strip()
        if not q:
            return ""

        # ---- stage