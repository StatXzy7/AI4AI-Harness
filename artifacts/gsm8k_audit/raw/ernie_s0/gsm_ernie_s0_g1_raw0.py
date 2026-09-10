"""Self-consistency via temperature-sampled majority voting over 5 independent generations to improve answer reliability."""

from ..harness_base import MathHarness
from collections import Counter
import re


class GsmGsmErnieS0G1(MathHarness):
    def solve(self, question: str) -> str:
        # Prompt the frozen solver with standard MATH-500 style instructions
        prompt = (
            f"Solve the following math problem step by step. "
            f"Put your final answer on the last line in the form '#### <answer>'.\n\n"
            f"Problem: {question}"
        )

        # Self-consistency: sample 5 times with temperature > 0 to get diverse outputs
        answers = []
        for _ in range(5):
            response = self.llm(prompt, system="", temperature=0.7, n=1)
            answer = self._extract_answer(response)
            if answer is not None:
                answers.append(answer)

        # Fallback: if all extractions failed, try one greedy pass
        if not answers:
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            answer = self._extract_answer(response)
            if answer is not None:
                answers.append(answer)

        # Majority vote: pick the most common answer
        if answers:
            counter = Counter(answers)
            most_common = counter.most_common(1)[0][0]
            return most_common

        # Last resort: return empty string
        return ""

    def _extract_answer(self, text: str) -> str:
        """Extract the answer from '#### <answer>' pattern on the last matching line."""
        # Find all occurrences of #### pattern
        matches = re.findall(r'####\s*(.+)', text)
        if not matches:
            return None
        # Take the last one (should be the final answer)
        raw = matches[-1].strip()
        # Clean up: remove trailing punctuation, whitespace, newlines
        raw = raw.rstrip('.,;!?\n')
        return raw