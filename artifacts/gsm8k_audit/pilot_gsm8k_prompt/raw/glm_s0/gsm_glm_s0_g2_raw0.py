"""Adaptive self-consistency: sample a batch of chain-of-thought solutions and majority-vote their extracted final numbers, escalating to a greedy anchor plus a second sample batch (with greedy/median tie-breaks) only when the first batch lacks consensus."""

import re
from collections import Counter
from typing import List, Optional

from ..harness_base import MathHarness

__all__ = ["GsmGsmGlmS0G2"]


class GsmGsmGlmS0G2(MathHarness):
    """Replaces a single greedy call with adaptive self-consistency voting.

    Control flow of ``solve``:
      1. Draw ``FIRST_BATCH`` temperature-sampled chain-of-thought solutions and
         extract each final number ("#### n", "answer is n", or last number).
      2. Strong consensus (>= ``EARLY_EXIT_VOTES``) returns immediately.
      3. Otherwise escalate: one greedy (temperature 0) anchor plus
         ``SECOND_BATCH`` more samples; pool every extracted answer, give the
         greedy answer a bonus vote, and return the plurality answer.
      4. Remaining ties break toward the greedy answer, then the median numeric
         value, then the earliest-seen leader.
    """

    FIRST_BATCH = 5            # samples drawn before deciding whether to escalate
    SECOND_BATCH = 5           # extra samples when the first batch disagrees
    EARLY_EXIT_VOTES = 4       # consensus needed to skip escalation entirely
    SAMPLE_TEMPERATURE = 0.7   # diversity knob for the sampled chains

    SYSTEM = (
        "You are a careful grade-school math tutor. Reason step by step, keep "
        "every arithmetic step explicit, and end your reply with the final "
        "numeric answer alone on the last line in the exact format "
        "'#### <number>'."
    )

    PROMPT_TEMPLATE = (
        "Solve this math word problem step by step.\n"
        "End with the final answer on its own last line as '#### <number>'.\n\n"
        "Problem:\n{question}\n\nSolution:"
    )

    # A number token: optional sign, optional currency symbol, digits with
    # optional thousands commas, optional decimal part.
    _NUM = r"-?\$?\d[\d,]*(?:\.\d+)?"
    _ANSWER_PATTERNS = (
        r"####\s*(" + _NUM + r")",                            # GSM8K marker
        r"answer(?:\s+is)?\s*[:=]?\s*\**\s*(" + _NUM + r")",  # prose forms
    )

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        prompt = self._prompt(question)

        # ---- Stage 1: first batch of diverse samples --------------------
        stage1_texts = self._generate(prompt, self.SAMPLE_TEMPERATURE, self.FIRST_BATCH)
        stage1_answers = [
            a for a in (self._extract_answer(t) for t in stage1_texts) if a is not None
        ]
        if stage1_answers:
            top_answer, top_votes = Counter(stage1_answers).most_common(1)[0]
            if top_votes >= self.EARLY_EXIT_VOTES:
                return top_answer  # strong consensus: stop early, save calls

        # ---- Stage 2: disagreement (or nothing parseable) -> escalate ----
        greedy_texts = self._generate(prompt, 0.0, 1)
        greedy_text = greedy_texts[0] if greedy_texts else ""
        greedy_answer = self._extract_answer(greedy_text)

        stage2_texts = self._generate(prompt, self.SAMPLE_TEMPERATURE, self.SECOND_BATCH)
        stage2_answers = [
            a for a in (self._extract_answer(t) for t in stage2_texts) if a is not None
        ]

        votes = stage1_answers + stage2_answers
        if greedy_answer is not None:
            votes.append(greedy_answer)

        if not votes:
            # Nothing parseable anywhere: best-effort raw tail of a reply.
            return self._last_resort(greedy_text, stage1_texts + stage2_texts)

        counts = Counter(votes)
        if greedy_answer is not None:
            counts[greedy_answer] += 1  # greedy anchor casts a bonus vote

        best = max(counts.values())
        leaders = [answer for answer, count in counts.items() if count == best]

        if len(leaders) == 1:
            return leaders[0]
        if greedy_answer is not None and greedy_answer in leaders:
            return greedy_answer  # tie-break 1: trust the greedy anchor
        numeric = [a for a in leaders if self._to_float(a) is not None]
        if numeric:  # tie-break 2: median numeric value among leaders
            numeric.sort(key=self._to_float)
            mid = len(numeric) // 2
            return numeric[mid] if len(numeric) % 2 else numeric[mid - 1]
        for answer in votes:  # tie-break 3: earliest seen
            if answer in leaders:
                return answer
        return leaders[0]

    # ------------------------------------------------------------ plumbing

    def _prompt(self, question: str) -> str:
        return self.PROMPT_TEMPLATE.format(question=question.strip())

    def _generate(self, prompt: str, temperature: float, n: int) -> List[str]:
        """Return ``n`` completions, topping up if a backend collapses batching."""
        if n <= 0:
            return []
        texts = self._call(prompt, temperature, n)
        attempts = 0
        while len(texts) < n and attempts < n:
            attempts += 1
            texts.extend(self._call(prompt, temperature, 1))
        return texts[:n]

    def _call(self, prompt: str, temperature: float, n: int) -> List[str]:
        try:
            out = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=n)
        except TypeError:
            if n == 1:
                raise  # backend rejects something else; surface the error
            out = [
                self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
                for _ in range(n)
            ]
        return self._as_texts(out)

    @classmethod
    def _as_texts(cls, out) -> List[str]:
        """Normalize an llm() return value into a flat list of strings."""
        if out is None:
            return []
        if isinstance(out, str):
            return [out]
        if isinstance(out, dict):
            for key in ("choices", "completions", "texts", "generations", "candidates"):
                value = out.get(key)
                if isinstance(value, (list, tuple)):
                    return cls._as_texts(value)
            for key in ("text", "content", "response", "output"):
                value = out.get(key)
                if isinstance(value, str):
                    return [value]
            return []
        if isinstance(out, (list, tuple)):
            texts: List[str] = []
            for item in out:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, (list, tuple, dict)):
                    texts.extend(cls._as_texts(item))
            return texts
        return [str(out)]

    # ------------------------------------------------------- answer parsing

    @classmethod
    def _extract_answer(cls, text: Optional[str]) -> Optional[str]:
        """Pull the final numeric answer out of one