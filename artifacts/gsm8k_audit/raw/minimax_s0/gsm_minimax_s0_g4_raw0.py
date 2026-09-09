"""Self-consistency with lightweight answer extraction and majority voting across sampled solver outputs."""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional, Tuple

from ..harness_base import MathHarness


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _extract_answer(text: str) -> Optional[float]:
    """Extract a numeric answer from a solver reply, trying multiple conventions."""
    if not text:
        return None

    # Prefer an explicit "#### N" marker when present.
    hash_match = re.search(r"####\s*(-?\d+(?:,\d{3})*(?:\.\d+)?)", text)
    if hash_match:
        return _to_float(hash_match.group(1))

    # Otherwise prefer "The answer is N" style phrasings.
    phrase = re.findall(
        r"(?:the\s+answer\s+is|answer\s*[:=])\s*\$?\s*(-?\d+(?:,\d{3})*(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if phrase:
        return _to_float(phrase[-1])

    # Fallback: the last number in the text (solver often summarizes a number at the end).
    nums = _NUM_RE.findall(text)
    if nums:
        return _to_float(nums[-1])

    return None


def _to_float(token: str) -> Optional[float]:
    cleaned = token.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _format_answer(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


class GsmGsmMinimaxS0G4(MathHarness):
    """Self-consistency wrapper: sample multiple solver replies and majority-vote their extracted answers."""

    NUM_SAMPLES = 5
    FALLBACK_TEMPERATURE = 0.7

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)

        # First try a deterministic greedy decode; if it yields a parseable answer,
        # still gather samples so we can confirm with self-consistency when possible.
        samples: List[str] = []

        try:
            greedy_reply = self.llm(prompt, system=self._system_prompt(),
                                     temperature=0.0, n=1)
        except TypeError:
            greedy_reply = self.llm(prompt, system=self._system_prompt())
        if greedy_reply:
            samples.append(greedy_reply)

        # Stochastic sampling for self-consistency. Use n=NUM_SAMPLES with
        # non-zero temperature; if the harness does not support `n`, fall back
        # to looping individual calls so the mechanism still works.
        try:
            extra = self.llm(prompt, system=self._system_prompt(),
                             temperature=self.FALLBACK_TEMPERATURE,
                             n=self.NUM_SAMPLES)
        except TypeError:
            extra = None

        if isinstance(extra, list) and extra:
            samples.extend(extra)
        else:
            for _ in range(self.NUM_SAMPLES):
                try:
                    reply = self.llm(prompt, system=self._system_prompt(),
                                     temperature=self.FALLBACK_TEMPERATURE, n=1)
                except TypeError:
                    reply = self.llm(prompt, system=self._system_prompt())
                if reply:
                    samples.append(reply)

        final = self._aggregate(samples)
        return final

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _system_prompt(self) -> str:
        return (
            "You are a careful grade-school math tutor. Solve the problem "
            "step by step, then on the final line write the answer in the "
            "form '#### <number>'."
        )

    def _build_prompt(self, question: str) -> str:
        return (
            "Solve the following grade-school math word problem.\n"
            "Show your reasoning briefly, then state the final answer on the "
            "last line as '#### <number>'.\n\n"
            f"Problem: {question.strip()}\n\nSolution:"
        )

    def _aggregate(self, samples: List[str]) -> str:
        parsed: List[Tuple[float, str]] = []
        for s in samples:
            v = _extract_answer(s)
            if v is not None:
                parsed.append((v, _format_answer(v)))

        if not parsed:
            # Nothing parseable: return the last sample's tail as a best effort
            # so the harness still produces something string-like.
            tail = (samples[-1] if samples else "").strip()
            fallback = _NUM_RE.findall(tail)
            if fallback:
                return _format_answer(_to_float(fallback[-1]))
            return tail or ""

        # Majority vote on the canonical string form, breaking ties by greedy sample order.
        counter = Counter(formatted for _, formatted in parsed)
        most_common, count = counter.most_common(1)[0]

        # If the greedy sample agrees with the majority, keep it (it was the
        # first seen). Otherwise pick the first sampled instance of the
        # majority value to preserve determinism.
        greedy_value = parsed[0][1] if parsed else None
        if greedy_value == most_common:
            return greedy_value

        for value, formatted in parsed:
            if formatted == most_common:
                return formatted

        return most_common