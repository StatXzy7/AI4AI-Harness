"""Self-consistency ensemble with a greedy fallback: sample five high-temperature solutions, extract numeric answers, and return the majority answer."""
import re
from collections import Counter
from typing import Optional

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G5(MathHarness):
    def solve(self, question: str) -> str:
        prompt = question

        # Greedy answer is a stable fallback.
        greedy_text = self._call_single(prompt, temperature=0.0)
        greedy_answer = self._extract_answer(greedy_text)

        # Diverse sampling for self-consistency.
        sample_answers = []
        for _ in range(5):
            text = self._call_single(prompt, temperature=0.8)
            answer = self._extract_answer(text)
            if answer is not None:
                sample_answers.append(answer)

        if sample_answers:
            counts = Counter(sample_answers)
            top_answer, top_count = counts.most_common(1)[0]
            # Require agreement among at least two sampled paths; otherwise
            # a single high-temperature sample is too noisy.
            if top_count >= 2:
                return top_answer

        if greedy_answer is not None:
            return greedy_answer
        return sample_answers[0] if sample_answers else ""

    def _call_single(self, prompt: str, temperature: float) -> str:
        result = self.llm(prompt, system="", temperature=temperature, n=1)
        if isinstance(result, list):
            return str(result[0]) if result else ""
        return str(result or "")

    @staticmethod
    def _extract_answer(text: str) -> Optional[str]:
        if not text:
            return None

        # Preferred: explicit GSM8K hash-final answer.
        hash_matches = re.findall(
            r"####\s*([-+]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+))",
            text,
        )
        if hash_matches:
            return hash_matches[-1].replace(",", "")

        # Next: explicit answer phrases.
        answer_matches = re.findall(
            r"(?:the\s+)?(?:final\s+)?answer\s*(?:is|=|:)?\s*"
            r"([-+]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+))",
            text,
            re.IGNORECASE,
        )
        if answer_matches:
            return answer_matches[-1].replace(",", "")

        # Next: last equality.
        eq_matches = re.findall(
            r"=\s*([-+]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+))",
            text,
        )
        if eq_matches:
            return eq_matches[-1].replace(",", "")

        # Fallback: last number on the last non-empty line.
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        if lines:
            last_line = lines[-1]
            nums = re.findall(
                r"[-+]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)",
                last_line,
            )
            if nums:
                return nums[-1].replace(",", "")

        # Last fallback: last number anywhere in the text.
        nums = re.findall(
            r"[-+]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)",
            text,
        )
        if nums:
            return nums[-1].replace(",", "")
        return None