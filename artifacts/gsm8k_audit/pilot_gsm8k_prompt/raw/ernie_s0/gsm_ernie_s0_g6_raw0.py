"""Uses self-consistency by generating multiple stochastic completions and returning the majority-voted numerical answer."""

from ..harness_base import MathHarness
import re
from collections import Counter


class GsmGsmErnieS0G6(MathHarness):
    def solve(self, question: str) -> str:
        # Self-consistency: generate multiple diverse completions and majority-vote.
        num_generations = 5
        answers = []

        for i in range(num_generations):
            prompt = (
                f"{question}\n\n"
                f"Solve this grade-school math problem step by step. "
                f"Put your final numerical answer on its own line, "
                f"either as '#### <number>' or 'The answer is <number>'."
            )
            response = self.llm(prompt, system="", temperature=0.7, n=1)
            answer = self._extract_answer(response)
            if answer is not None:
                answers.append(answer)

        if not answers:
            # Fallback: single greedy generation if extraction failed every time.
            prompt = (
                f"{question}\n\n"
                f"Solve this grade-school math problem step by step. "
                f"Put your final numerical answer on its own line, "
                f"either as '#### <number>' or 'The answer is <number>'."
            )
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            answer = self._extract_answer(response)
            return answer if answer is not None else "0"

        # Majority vote on extracted numerical answers.
        counter = Counter(answers)
        most_common_answer = counter.most_common(1)[0][0]
        return most_common_answer

    def _extract_answer(self, text: str) -> str:
        """Extract the final numerical answer from solver output."""
        # Pattern 1: "#### 42" or "#### -3.5"
        match = re.search(r"####\s*(-?\d+(?:\.\d+)?)", text)
        if match:
            return match.group(1)

        # Pattern 2: "The answer is 42"
        match = re.search(r"[Tt]he answer is\s*(-?\d+(?:\.\d+)?)", text)
        if match:
            return match.group(1)

        # Pattern 3: last standalone number in the text (e.g., ends with "42")
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*$", text.strip())
        if match:
            return match.group(1)

        return None