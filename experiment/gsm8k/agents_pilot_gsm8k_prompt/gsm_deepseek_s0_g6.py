"""Six temperature-0.6 completions are sampled, numeric answers are extracted, and majority vote is returned with a greedy fallback."""
import re
from collections import Counter
from ..harness_base import MathHarness


class GsmGsmDeepseekS0G6(MathHarness):
    _SAMPLE_COUNT = 6
    _SAMPLE_TEMPERATURE = 0.6

    def solve(self, question: str) -> str:
        prompt = question
        candidates = []

        for _ in range(self._SAMPLE_COUNT):
            try:
                text = self._call(prompt, temperature=self._SAMPLE_TEMPERATURE)
                answer = self._extract_answer(text)
                if answer is not None:
                    candidates.append(answer)
            except Exception:
                continue

        if candidates:
            votes = Counter(candidates)
            winner, count = votes.most_common(1)[0]
            if count >= 2:
                return str(winner)

        fallback_text = self._call(prompt, temperature=0.0)
        answer = self._extract_answer(fallback_text)
        if answer is not None:
            return str(answer)

        return "0"

    def _call(self, prompt: str, temperature: float, system: str = "") -> str:
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=1)
        except TypeError:
            response = self.llm(prompt, temperature=temperature, n=1)

        if isinstance(response, list):
            if response:
                return str(response[0])
            return ""
        if isinstance(response, str):
            return response
        if hasattr(response, "text"):
            return str(response.text)
        return str(response)

    @staticmethod
    def _extract_answer(text: str):
        if not text:
            return None

        patterns = [
            r"####\s*(-?\d+(?:[,.]\d+)?)",
            r"answer\s+is\s*(-?\d+(?:[,.]\d+)?)",
            r"answer\s*[:=]?\s*(-?\d+(?:[,.]\d+)?)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, flags=re.IGNORECASE)
            if matches:
                return GsmGsmDeepseekS0G6._normalize(matches[-1])

        numbers = re.findall(r"-?\d+(?:[,.]\d+)?", text)
        if numbers:
            return GsmGsmDeepseekS0G6._normalize(numbers[-1])

        return None

    @staticmethod
    def _normalize(answer: str) -> str:
        answer = answer.strip().replace(",", "")
        try:
            if "." in answer:
                value = float(answer)
                if value.is_integer():
                    return str(int(value))
        except (ValueError, OverflowError):
            pass
        return answer