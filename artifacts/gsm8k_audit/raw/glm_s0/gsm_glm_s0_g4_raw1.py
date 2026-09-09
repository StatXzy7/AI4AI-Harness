"""Self-consistency harness for GSM8K that replaces single greedy decoding with one greedy anchor plus several temperature-sampled solutions, a confidence-weighted majority vote over extracted final answers, and an extra greedy verification call to break near-ties between the top two candidates."""

import re
from typing import Any, Dict, List, Optional, Tuple

from ..harness_base import MathHarness

__all__ = ["GsmGsmGlmS0G4"]


class GsmGsmGlmS0G4(MathHarness):
    """GSM8K harness wrapping a frozen solver with a self-consistency loop.

    Control flow (a real change vs. one greedy call):

    1. **Greedy anchor** -- one deterministic chain-of-thought solution is
       generated at temperature 0.
    2. **Diverse sampling** -- ``NUM_SAMPLES`` additional solutions are drawn
       at ``SAMPLE_TEMPERATURE`` to explore different reasoning paths.
    3. **Extraction + voting** -- each reply's final answer is extracted
       (``#### n`` marker, "answer is n" phrasing, or last-number fallback),
       normalized to a canonical numeric string, and cast as a vote whose
       weight depends on extraction confidence.
    4. **Ranked election** -- the winner is chosen by weighted majority,
       with tie-breaks by raw vote count, marker quality, agreement with the
       greedy anchor, then order of first appearance.
    5. **Adaptive verification** -- if the top two candidates are within
       ``TIE_MARGIN`` of each other, one extra greedy call re-solves the
       problem while explicitly comparing the two contenders, and its
       verdict boosts the matching candidate before the final ranking.
    """

    # ----------------------------- tunables ----------------------------- #
    NUM_SAMPLES = 5            # sampled reasoning paths beyond the greedy anchor
    SAMPLE_TEMPERATURE = 0.7   # sampling temperature for the diverse paths
    TIE_MARGIN = 0.5           # weight gap that triggers verification
    VERIFICATION_WEIGHT = 2.0  # boost applied to the verified candidate

    SYSTEM = (
        "You are a careful math tutor who solves math word problems "
        "step by step and always double-checks the arithmetic."
    )

    PROMPT_TEMPLATE = (
        "Solve the following grade-school math problem step by step.\n"
        "Keep the reasoning short and check your arithmetic.\n"
        "End your reply with the final numeric answer on its own last line "
        "in the exact format:\n"
        "#### <number>\n\n"
        "Problem:\n{question}"
    )

    VERIFY_TEMPLATE = (
        "Problem:\n{question}\n\n"
        "Two different final answers were proposed:\n"
        "(A) {a}\n(B) {b}\n\n"
        "Only one of them is correct. Carefully re-solve the problem step by "
        "step, then end your reply with a line in the exact format:\n"
        "#### <number>\n"
        "where <number> is the correct final answer (it must equal A or B)."
    )

    # ------------------------------ parsing ----------------------------- #
    _HASH_RE = re.compile(r"####\s*([^\n]+)")
    _ANSWER_RE = re.compile(
        r"(?:final\s+answer|answer)\s*(?:is|:|=|should\s+be)\s*\$?\s*"
        r"(-?[\d,]+(?:\.\d+)?(?:\s*/\s*\d+)?)",
        re.IGNORECASE,
    )
    _NUM_RE = re.compile(r"(?<!\d)-?\$?(?:\d[\d,]*(?:\.\d+)?|\.\d+)")
    _FRACTION_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)")
    _LEADING_NUM_RE = re.compile(r"(-?\d+(?:\.\d+)?)")
    _CHOICE_RE = re.compile(r"correct\s+answer\s+is\s*\(?([AB])\)?", re.IGNORECASE)

    # ------------------------------ public ------------------------------ #
    def solve(self, question: str) -> str:
        prompt = self.PROMPT_TEMPLATE.format(question=question.strip())

        # 1) Greedy anchor: one deterministic reasoning path.
        greedy_text = self._call(prompt, temperature=0.0)
        greedy_answer, _ = self._extract(greedy_text)

        # 2) Diverse sampled reasoning paths.
        texts = [greedy_text] + self._sample(
            prompt, self.SAMPLE_TEMPERATURE, self.NUM_SAMPLES
        )

        # 3) Weighted majority vote over extracted final answers.
        votes: Dict[str, Dict[str, Any]] = {}
        for index, text in enumerate(texts):
            answer, confidence = self._extract(text)
            if answer is None:
                continue
            record = votes.setdefault(
                answer,
                {"weight": 0.0, "count": 0, "strong": 0, "first": index},
            )
            record["weight"] += 1.0 + confidence
            record["count"] += 1
            if confidence >= 1.0:
                record["strong"] += 1

        if not votes:
            # Nothing extractable anywhere: fall back to any visible number.
            for text in texts:
                fallback = self._last_number(text)
                if fallback is not None:
                    return fallback
            return ""

        ranked = self._rank(votes, greedy_answer)

        # 4) Adaptive tie-break: near-ties trigger a verification call.
        if len(ranked) > 1:
            (top_answer, top_record) = ranked[0]
            (runner_up, runner_record) = ranked[1]
            if top_record["weight"] - runner_record["weight"] <= self.TIE_MARGIN:
                verdict = self._verify(question, top_answer, runner_up)
                if verdict is not None and verdict in votes:
                    votes[verdict]["weight"] += self.VERIFICATION_WEIGHT
                    ranked = self._rank(votes, greedy_answer)

        return ranked[0][0]

    # ---------------------------- solver I/O ---------------------------- #
    def _call(self, prompt: str, temperature: float) -> str:
        """One call to the frozen solver, coerced to plain text ('' on failure)."""
        try:
            out = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
        except TypeError:
            # Solver signature may not accept every keyword.
            try:
                out = self.llm(prompt, temperature=temperature)
            except Exception:
                return ""
        except Exception:
            return ""
        return self._to_text(out)

    def _sample(self, prompt: str, temperature: float, count: int) -> List[str]:
        """Collect ``count`` completions, batching when the solver supports ``n>1``."""
        texts: List[str] = []
        try:
            out = self.llm(
                prompt,
                system=self.SYSTEM,
                temperature=temperature,
                n=count,
            )
        except Exception:
            out = None
        if out is not None:
            if isinstance(out, (list, tuple)):
                texts = [self._to_text(item) for item in out]
            else:
                single = self._to_text(out)
                if single:
                    texts = [single]
        # Top up one-by-one if the batched call yielded fewer than requested.
        while len(texts) < count:
            texts.append(self._call(prompt, temperature=temperature))
        return texts[:count]

    @classmethod
    def _to_text(cls, out: Any) -> str:
        """Coerce a single solver reply (str / list / object) to a string."""
        if isinstance(out, (list, tuple)):
            if not out:
                return ""
            out = out[0]
        if isinstance(out, str):
            return out
        for attribute in ("text", "content"):
            value = getattr(out, attribute, None)
            if isinstance(value, str):
                return value
        return "" if out is None else str(out)

    # ---------------------------- extraction ---------------------------- #
    def _extract(self, text: str) -> Tuple[Optional[str], float]:
        """Extract ``(canonical_answer, confidence)`` from one solver reply.

        Confidence: 1.0 for an explicit ``#### n`` marker, 0.6 for
        "the answer is n" phrasing, 0.3 for a last-number fallback.
        """
        if not text:
            return None, 0.0
        hash_matches = list(self._HASH_RE.finditer(text))
        if hash_matches:
            answer = self._normalize(hash_matches[-1].group(1))
            if answer is not None:
                return answer, 1.0
        answer_matches = list(self._ANSWER_RE.finditer(text))
        if answer_matches:
            answer = self._normalize(answer_matches[-1].group(1))
            if answer is not None:
                return answer, 0.6
        answer = self._last_number(text)
        if answer is not None:
            return answer, 0.3
        return None, 0.0

    def _last_number(self, text: str) -> Optional[str]:
        """Last number appearing anywhere in the text, normalized."""
        if not text:
            return None
        matches = self._NUM_RE.findall(text)
        if not matches:
            return None
        return self._normalize(matches[-1])

    def _normalize(self, raw: Any) -> Optional[str]:
        """Canonicalize a raw answer snippet ('$1,234.50', '42 dollars') to a
        plain numeric string ('1234.5', '42'); returns None if no number."""
        if raw is None:
            return None
        s = str(raw).strip()
        s = s.replace("$", "").replace("%", "").replace(",", "")
        s = s.strip().rstrip(".")
        if not s:
            return None
        fraction = self._FRACTION_RE.fullmatch(s)
        if fraction:
            try:
                value = float(fraction.group(1)) / float(fraction.group(2))
            except ZeroDivisionError:
                return None
            return self._format(value)
        leading = self._LEADING_NUM_RE.match(s)
        if not leading:
            return None
        return self._format(float(leading.group(1)))

    @staticmethod
    def _format(value: float) -> str:
        """Render a float canonically: integers without a decimal part."""
        if abs(value - round(value)) < 1e-9:
            return str(int(round(value)))
        return repr(round(value, 6))

    # ----------------------------- voting ------------------------------- #
    def _rank(
        self,
        votes: Dict[str, Dict[str, Any]],
        greedy_answer: Optional[str],
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Order candidates by weight, then count, marker strength, greedy
        agreement, and finally order of first appearance."""
        return sorted(
            votes.items(),
            key=lambda item: (
                -item[1]["weight"],
                -item[1]["count"],
                -item[1]["strong"],
                0 if item[0] == greedy_answer else 1,
                item[1]["first"],
            ),
        )

    # --------------------------- verification --------------------------- #
    def _verify(self, question: str, a: str, b: str) -> Optional[str]:
        """Ask the frozen solver to adjudicate between two contenders.

        Returns the winning candidate's canonical string (or None if the
        verdict is unusable).
        """
        prompt = self.VERIFY_TEMPLATE.format(
            question=question.strip(), a=a, b=b
        )
        text = self._call(prompt, temperature=0.0)
        answer, _ = self._extract(text)
        if answer is not None and answer in (a, b):
            return answer
        # Fallback: the reply may name the choice explicitly.
        match = self._CHOICE_RE.search(text)
        if match:
            return a if match.group(1).upper() == "A" else b
        return None