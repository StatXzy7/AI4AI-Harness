"""Self-verifying solver that samples a candidate answer, then re-prompts to critique and refine it before locking in the final response."""
from __future__ import annotations

import re
from typing import Optional

from ..harness_base import MathHarness


_ANSWER_RE = re.compile(r"####\s*(.+?)\s*$", re.MULTILINE)


def _extract_answer(text: str) -> Optional[str]:
    """Pull the last '#### <answer>' line out of a model response, if present."""
    if not text:
        return None
    matches = _ANSWER_RE.findall(text)
    if not matches:
        return None
    return matches[-1].strip()


def _strip_to_text(answer: str) -> str:
    """Compact an extracted answer by stripping LaTeX dollar signs and whitespace."""
    if answer is None:
        return ""
    a = answer.strip()
    # Remove surrounding $...$ if the model wrapped the answer inline
    if a.startswith("$") and a.endswith("$"):
        a = a[1:-1].strip()
    return a


class GsmGsmMinimaxS0G0(MathHarness):
    """
    Solve MATH-500 style competition problems via a two-stage "draft + critique"
    protocol:

      Stage 1 -- DRAFT
          Sample a greedy solution at temperature 0 and harvest the
          '#### <answer>' line. We also retain the model's reasoning so
          the critic can point at specific lines.

      Stage 2 -- CRITIQUE / VERIFY
          Re-prompt the frozen solver (still temperature 0) with a short
          verification rubric: restate the problem, judge the draft's
          arithmetic and reasoning, and either CONFIRM the draft's answer
          or REPLACE it with a corrected one. The new response must again
          end with '#### <answer>'.

      Stage 3 -- SELECT
          Prefer the critique's final answer. As a lightweight consistency
          check, if the draft and critique disagree, we ask the solver one
          more time to pick between them ("self-consistency vote" with n=1);
          the resulting answer wins. If the critique response fails to
          produce an '####' line we fall back to the draft.

    The frozen LLM is never fine-tuned or asked to change its decoding
    settings -- only the *control flow* around it changes.
    """

    # --- prompt templates -------------------------------------------------

    _CRITIQUE_TEMPLATE = (
        "You are verifying a candidate solution to a math problem.\n\n"
        "PROBLEM:\n{question}\n\n"
        "DRAFT SOLUTION:\n{draft}\n\n"
        "Your task:\n"
        "1. Re-read the problem carefully and identify what is being asked.\n"
        "2. Walk through the draft step by step. Point out any arithmetic,\n"
        "   algebraic, or logical errors. If you find an error, compute the\n"
        "   correct value.\n"
        "3. End your response with exactly one line of the form\n"
        "   '#### <answer>'\n"
        "   where <answer> is the final, correct answer (use LaTeX such as\n"
        "   \\frac{{3}}{{4}}, 2\\sqrt{{3}}, (3,4], etc. as appropriate).\n"
        "   If the draft is fully correct, repeat its answer on that line.\n\n"
        "VERIFICATION:"
    )

    _TIEBREAK_TEMPLATE = (
        "Two candidate answers were produced for the same math problem.\n"
        "Pick the one that is actually correct, and respond with ONLY one\n"
        "line of the form:\n\n"
        "#### <answer>\n\n"
        "PROBLEM:\n{question}\n\n"
        "CANDIDATE A: {a}\n"
        "CANDIDATE B: {b}\n\n"
        "Choose the correct candidate and output the '####' line:"
    )

    # ---------------------------------------------------------------------

    def solve(self, question: str) -> str:
        # ---- Stage 1: greedy draft --------------------------------------
        draft_prompt = (
            "Solve the following math problem. Show clear reasoning, then "
            "place your final answer on the last line in the form "
            "'#### <answer>'.\n\n"
            f"PROBLEM:\n{question}\n\n"
            "SOLUTION:"
        )
        draft_resp = self.llm(draft_prompt, system="", temperature=0.0, n=1)
        draft_answer = _strip_to_text(_extract_answer(draft_resp) or "")

        if not draft_answer:
            # The frozen solver didn't follow the format -- return whatever
            # it gave so we don't crash on a malformed problem.
            return (draft_resp or "").strip()

        # ---- Stage 2: critique / verification ----------------------------
        critique_prompt = self._CRITIQUE_TEMPLATE.format(
            question=question, draft=draft_resp
        )
        critique_resp = self.llm(critique_prompt, system="", temperature=0.0, n=1)
        critique_answer = _strip_to_text(_extract_answer(critique_resp) or "")

        if not critique_answer:
            # Critic failed to produce a parseable answer; trust the draft.
            return draft_answer

        # ---- Stage 3: consistency vote on disagreement -------------------
        if critique_answer == draft_answer:
            return critique_answer

        tiebreak_prompt = self._TIEBREAK_TEMPLATE.format(
            question=question, a=draft_answer, b=critique_answer
        )
        tiebreak_resp = self.llm(
            tiebreak_prompt, system="", temperature=0.0, n=1
        )
        tiebreak_answer = _strip_to_text(_extract_answer(tiebreak_resp) or "")

        if not tiebreak_answer:
            # Default tie-break: trust the critic over the original draft.
            return critique_answer

        # If the tiebreaker echoed one of the two candidates, prefer that
        # explicit match; otherwise return whatever the tiebreaker produced.
        if tiebreak_answer in (draft_answer, critique_answer):
            return tiebreak_answer
        return tiebreak_answer