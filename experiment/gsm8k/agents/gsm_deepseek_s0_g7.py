"""Use self-consistency over multiple sampled solver calls and majority vote on extracted final numeric answers."""
import re
from collections import Counter
from typing import Optional

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G7(MathHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Solve the following grade-school math word problem.\n"
            "Think step by step, then write the final answer on the last line as '#### <number>'.\n\n"
            f"Question: {question}\n"
        )

        responses = []
        for _ in range(5):
            response = self.llm(prompt, system="", temperature=0.7, n=1)
            responses.append(response)

        answers = []
        for response in responses:
            extracted = self._extract_answer(response)
            if extracted is not None:
                answers.append(extracted)

        if answers:
            return self._majority_vote(answers)

        # Fallback to a single greedy call if no sample produced a usable number.
        fallback_response = self.llm(prompt, system="", temperature=0.0, n=1)
        fallback_answer = self._extract_answer(fallback_response)
        if fallback_answer is not None:
            return fallback_answer

        # Last-resort scan over the already-sampled responses for any numeric token.
        for response in responses:
            numbers = re.findall(r"-?\d+(?:,\d{3})*(?:\.\d+)?", response)
            if numbers:
                return self._normalize_number(numbers[-1])

        return ""

    def _extract_answer(self, text: str) -> Optional[str]:
        if not text:
            return None

        # Prefer the conventional end-of-answer marker.
        match = re.search(r"####\s*(-?[\d,]+(?:\.\d+)?)", text)
        if match:
            return self._normalize_number(match.group(1))

        # Explicit answer phrases, taking the last one in the response.
        phrase_pattern = re.compile(
            r"\b(?:answer|result|final answer)\s*(?:is|:|=)\s*(-?[\d,]+(?:\.\d+)?)",
            re.IGNORECASE,
        )
        matches = phrase_pattern.findall(text)
        if matches:
            return self._normalize_number(matches[-1])

        # Fallback: last numeric token on the last non-empty line.
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        for line in reversed(lines):
            numbers = re.findall(r"-?\d+(?:,\d{3})*(?:\.\d+)?", line)
            if numbers:
                return self._normalize_number(numbers[-1])

        return None

    def _normalize_number(self, raw: str) -> str:
        value = raw.replace(",", "")
        if "." in value:
            try:
                numeric = float(value)
                if numeric.is_integer():
                    return str(int(numeric))
            except ValueError:
                pass
            return value.rstrip("0").rstrip(".") or "0"
        return value

    def _majority_vote(self, answers: list) -> str:
        counts = Counter(answers)
        max_count = max(counts.values())
        # Preserve first-occurrence tie breaking.
        for answer in answers:
            if counts[answer] == max_count:
                return answer
        return answers[0]