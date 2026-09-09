"""Self-verification wrapper: asks the frozen solver, extracts a candidate, then prompts it to double-check; if the verification disagrees, regenerates with an explicit correction context before committing the answer."""
from __future__ import annotations

import re
from typing import Optional

from ..harness_base import MathHarness


_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_GSM_HASH_RE = re.compile(r"####\s*(-?\d+(?:\.\d+)?)")
_ANSWER_IS_RE = re.compile(r"[Tt]he answer is\s*(-?\d+(?:\.\d+)?)")
_TRAILING_NUMBER_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*\.?\s*$")


def _extract_number(text: str) -> Optional[str]:
    """Find the most likely final numeric answer in a solver response."""
    if not text:
        return None
    # 1) Explicit GSM "#### N" marker (highest priority).
    m = _GSM_HASH_RE.search(text)
    if m:
        return m.group(1)
    # 2) "The answer is N" phrasing.
    m = _ANSWER_IS_RE.search(text)
    if m:
        return m.group(1)
    # 3) Last number on the last non-empty line.
    for line in reversed([ln.strip() for ln in text.strip().splitlines() if ln.strip()]):
        m = _TRAILING_NUMBER_RE.search(line)
        if m:
            return m.group(1)
        # Fallback: any number on the last line.
        nums = _NUMBER_RE.findall(line)
        if nums:
            return nums[-1]
    # 4) Absolute fallback: last number anywhere.
    nums = _NUMBER_RE.findall(text)
    return nums[-1] if nums else None


def _build_verify_prompt(question: str, candidate: str, prior_text: str) -> str:
    """Prompt the solver to re-check its prior answer against the question."""
    return (
        f"Problem:\n{question.strip()}\n\n"
        f"A previous attempt produced this reasoning and answer:\n"
        f"--- BEGIN PRIOR ATTEMPT ---\n{prior_text.strip()}\n"
        f"--- END PRIOR ATTEMPT ---\n\n"
        f"Please re-solve the problem from scratch (do NOT just agree with the "
        f"prior attempt). State your final numeric answer on the last line, "
        f"preferably using the format '#### N' or 'The answer is N'."
    )


def _build_correct_prompt(question: str, prior_text: str, prior_answer: str,
                          other_answer: str) -> str:
    """Prompt the solver with a heads-up that its prior answer is disputed."""
    return (
        f"Problem:\n{question.strip()}\n\n"
        f"Your previous answer was '{prior_answer}'. An independent re-check "
        f"suggested the answer should be '{other_answer}'. One of you is wrong.\n"
        f"--- BEGIN YOUR PRIOR REASONING ---\n{prior_text.strip()}\n"
        f"--- END YOUR PRIOR REASONING ---\n\n"
        f"Carefully re-solve the problem. Show your work, then on the final "
        f"line give the numeric answer, ideally as '#### N' or 'The answer is N'."
    )


class GsmGsmMinimaxS0G5(MathHarness):
    """Self-verification harness with one regeneration on disagreement."""

    MAX_VERIFY_ROUNDS = 1  # how many re-checks after the initial attempt

    def solve(self, question: str) -> str:
        # --- 1) Initial greedy attempt ---
        initial_prompt = (
            "Solve the following grade-school math word problem. Show your "
            "reasoning step by step, then give the final numeric answer on the "
            "last line, ideally as '#### N' or 'The answer is N'.\n\n"
            f"Problem: {question.strip()}"
        )
        first_text = self.llm(initial_prompt, system="", temperature=0.0, n=1)
        first_answer = _extract_number(first_text)
        if first_answer is None:
            # Couldn't parse a number at all -- try one regeneration with a
            # stricter instruction before giving up.
            retry_text = self.llm(
                initial_prompt
                + "\n\nYour response MUST end with a single line containing "
                  "only the number, e.g. '#### 42'.",
                system="", temperature=0.0, n=1,
            )
            first_answer = _extract_number(retry_text)
            if first_answer is None:
                return ""
            first_text = retry_text

        candidate = first_answer
        candidate_text = first_text

        # --- 2) Self-verification loop ---
        for _ in range(self.MAX_VERIFY_ROUNDS):
            verify_prompt = _build_verify_prompt(question, candidate, candidate_text)
            verify_text = self.llm(verify_prompt, system="", temperature=0.0, n=1)
            verify_answer = _extract_number(verify_text)
            if verify_answer is None:
                # Verification didn't yield a parseable number -- trust original.
                break
            if verify_answer == candidate:
                # Agreement: stop, this is our answer.
                break

            # Disagreement: regenerate with an explicit correction context.
            correct_prompt = _build_correct_prompt(
                question, candidate_text, candidate, verify_answer,
            )
            corrected_text = self.llm(
                correct_prompt, system="", temperature=0.0, n=1,
            )
            corrected_answer = _extract_number(corrected_text)
            if corrected_answer is None:
                # Give up on correction; pick whichever side appears more often.
                # Tie-break: keep the verifier's fresh answer.
                return verify_answer

            # Majority vote over (initial, verify, corrected). In a 2-vs-1 tie,
            # prefer the most recent consistent answer.
            votes = [candidate, verify_answer, corrected_answer]
            counts = {v: votes.count(v) for v in set(votes)}
            top = max(counts.values())
            winners = [v for v, c in counts.items() if c == top]
            if len(winners) == 1:
                candidate = winners[0]
                candidate_text = corrected_text
            else:
                # Tie: prefer the freshly corrected answer.
                candidate = corrected_answer
                candidate_text = corrected_text

        return candidate