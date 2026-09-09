"""Self-consistency majority voting over multiple temperature-diversified solver completions with a greedy-baseline tie-breaker."""
import re
from collections import Counter

from ..harness_base import MathHarness


class GsmGsmDeepseekS0G0(MathHarness):
    def solve(self, question: str) -> str:
        def _normalize(num):
            try:
                value = float(num)
                if value.is_integer():
                    return str(int(value))
            except (ValueError, OverflowError):
                pass
            return num

        def _parse_answer(text):
            if not isinstance(text, str):
                text = str(text)
            if not text:
                return None

            clean = text.replace(",", "")

            # Prefer the explicit GSM8K final-answer marker.
            m = re.search(r"####\s*([-+]?\d+(?:\.\d+)?)", clean)
            if m:
                return _normalize(m.group(1))

            # Next, try an explicit "answer is" or "Answer:" phrase.
            m = re.search(
                r"(?:The answer is|answer is|Answer:)\s*([-+]?\d+(?:\.\d+)?)",
                clean,
                re.IGNORECASE,
            )
            if m:
                return _normalize(m.group(1))

            # Fallback: use the last number appearing in the solver output.
            numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", clean)
            if numbers:
                return _normalize(numbers[-1])

            return None

        def _first_text(result):
            if isinstance(result, (list, tuple)):
                result = result[0] if result else ""
            if isinstance(result, str):
                return result
            if hasattr(result, "text"):
                return result.text
            if isinstance(result, dict) and "text" in result:
                return result["text"]
            return str(result)

        def _one_call(temperature):
            result = self.llm(
                prompt=question,
                system="",
                temperature=temperature,
                n=1,
            )
            return _first_text(result)

        # Baseline greedy generation.
        greedy_text = _one_call(0.0)
        greedy_answer = _parse_answer(greedy_text)

        # Diverse sampled generations.
        sampled_answers = []
        for _ in range(5):
            sampled_text = _one_call(0.7)
            answer = _parse_answer(sampled_text)
            if answer is not None:
                sampled_answers.append(answer)

        if not sampled_answers:
            return greedy_answer if greedy_answer is not None else ""

        counts = Counter(sampled_answers)
        most_common = counts.most_common()

        if len(most_common) == 1 or most_common[0][1] > most_common[1][1]:
            return most_common[0][0]

        # If sampled answers tie, fall back to the greedy answer if present.
        if greedy_answer is not None and greedy_answer in counts:
            return greedy_answer

        return most_common[0][0]