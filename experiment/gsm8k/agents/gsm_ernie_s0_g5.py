"""Implements self-consistency majority voting: generates N independent solutions and returns the most frequent final answer."""

from ..harness_base import MathHarness
from collections import Counter
import re


class GsmGsmErnieS0G5(MathHarness):
    def solve(self, question: str) -> str:
        """
        Solve a competition-math word problem using self-consistency.
        Generates multiple independent solutions and returns the majority answer.
        """
        num_samples = 5  # number of independent generations for majority vote
        prompt = (
            "Solve the following competition-style math problem. "
            "Show your reasoning step by step. "
            "Put your final answer on the last line in the form '#### <answer>'.\n\n"
            f"Problem: {question}"
        )

        answers = []
        for _ in range(num_samples):
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            answer = self._extract_answer(response)
            if answer is not None:
                answers.append(answer)

        if not answers:
            # Fallback: return the last generated answer even if unparseable
            return self._extract_answer(response) or "0"

        # Majority vote: return the most common answer
        vote_counts = Counter(answers)
        most_common_answer = vote_counts.most_common(1)[0][0]
        return most_common_answer

    def _extract_answer(self, text: str) -> str:
        """Extract the answer from '#### <answer>' format on the last such line."""
        # Find all occurrences of #### pattern
        matches = re.findall(r'####\s*(.+?)(?:\s*$|$)', text, re.MULTILINE | re.DOTALL)
        if not matches:
            return None
        # Return the last one (should be the final answer)
        raw = matches[-1].strip()
        # Remove trailing whitespace and newlines
        return raw.strip()