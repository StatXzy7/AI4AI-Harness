"""Self-consistency with majority voting over k samples drawn at low temperature, falling back to a greedy call if samples disagree or are unparsable."""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional

from ..harness_base import MathHarness


# Prompt that nudges the weak solver to produce the canonical "#### N" tail.
_GSM_SYSTEM = (
    "You are a careful grade-school math tutor. Solve the problem step by step, "
    "and on the final line write the answer in the exact form: #### <number>"
)


def _extract_answer(text: str) -> Optional[str]:
    """Pull the final numeric answer out of the solver's text.

    Recognises (in priority order):
      - the canonical '#### N' tail
      - 'the answer is N' / 'answer: N' phrases
      - the last number that appears on its own at end of line
    Returns the digits (possibly with a decimal point) as a string, or None.
    """
    if not text:
        return None

    # 1. Canonical GSM8K tail.
    tail = re.search(r"####\s*(-?\d+(?:\.\d+)?)", text)
    if tail:
        return tail.group(1)

    # 2. "The answer is N" / "answer: N".
    phrase = re.search(
        r"(?:the\s+answer\s+is|answer\s*[:=])\s*\$?\s*(-?\d+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if phrase:
        return phrase.group(1)

    # 3. Last standalone number on its own line.
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    for ln in reversed(lines):
        m = re.fullmatch(r"\$?\s*(-?\d+(?:\.\d+)?)\s*\.?\s*", ln)
        if m:
            return m.group(1)

    # 4. Last number anywhere in the text.
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    if nums:
        return nums[-1]
    return None


class GsmGsmMinimaxS0G2(MathHarness):
    """Self-consistency harness: sample k answers, take the majority, else fall back to greedy."""

    # Tunables. Kept as class constants so they can be inspected / overridden.
    K = 5                # number of sampled answers
    TEMP = 0.4           # non-zero temperature so samples can differ
    MAJORITY_FRACTION = 0.6   # require >= 60% agreement to trust the vote

    # ---------- internal helpers ----------

    def _ask(self, prompt: str, temperature: float) -> str:
        """Single call to the frozen solver."""
        return self.llm(prompt, system=_GSM_SYSTEM, temperature=temperature, n=1)

    def _sample_answers(self, question: str) -> List[str]:
        """Draw K samples and extract a numeric answer from each."""
        answers: List[str] = []
        for _ in range(self.K):
            raw = self._ask(question, temperature=self.TEMP)
            ans = _extract_answer(raw)
            if ans is not None:
                # Normalise: drop trailing ".0" so "42.0" == "42".
                if "." in ans:
                    try:
                        if float(ans) == int(float(ans)):
                            ans = str(int(float(ans)))
                    except ValueError:
                        pass
                answers.append(ans)
        return answers

    def _greedy_answer(self, question: str) -> Optional[str]:
        """One deterministic run as a tie-breaker / fallback."""
        raw = self._ask(question, temperature=0.0)
        return _extract_answer(raw)

    # ---------- public API ----------

    def solve(self, question: str) -> str:
        # Step 1: try self-consistency over K samples.
        samples = self._sample_answers(question)

        if samples:
            counts = Counter(samples)
            top_ans, top_n = counts.most_common(1)[0]
            # Majority means top_n covers >= MAJORITY_FRACTION of the parses.
            if top_n / len(samples) >= self.MAJORITY_FRACTION:
                return top_ans

        # Step 2: no clear majority (or no parses at all) -> fall back to greedy.
        fallback = self._greedy_answer(question)
        if fallback is not None:
            return fallback

        # Step 3: last resort. If the greedy parse also failed, but we did see
        # *some* answer among the samples, return the most common one.
        if samples:
            return Counter(samples).most_common(1)[0][0]

        # Truly nothing parseable: return the raw greedy text trimmed, so the
        # caller still gets *something* rather than an empty string.
        raw = self._ask(question, temperature=0.0)
        return raw.strip()