"""Uses self-consistency by generating multiple independent chain-of-thought solutions and returning the majority-vote numerical answer."""

from ..harness_base import MathHarness
import re
from collections import Counter


class GsmGsmErnieS0G2(MathHarness):
    def solve(self, question: str) -> str:
        """
        Generate num_samples independent solutions with varied temperature,
        extract the numerical answer from each, and return the most frequent one.
        Falls back to a single greedy call if no valid answers are extracted.
        """
        num_samples = 5
        answers = []

        for i in range(num_samples):
            # Vary temperature slightly across samples to encourage diversity
            temp = 0.5 + 0.3 * (i % 3)  # cycles through 0.5, 0.8, 0.5
            prompt = (
                f"Question: {question}\n\n"
                f"Solve this grade-school math problem step by step and "
                f"put your final numerical answer on a line starting with '####'.\n\n"
            )
            response = self.llm(prompt, system="", temperature=temp, n=1)
            extracted = self._extract_number(response)
            if extracted is not None:
                answers.append(extracted)

        # If extraction failed for all samples, fall back to a single greedy call
        if not answers:
            prompt = (
                f"Question: {question}\n\n"
                f"Solve this grade-school math problem step by step and "
                f"put your final numerical answer on a line starting with '####'.\n\n"
            )
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            extracted = self._extract_number(response)
            return str(extracted) if extracted is not None else "0"

        # Majority vote: pick the most common answer
        counter = Counter(answers)
        most_common_answer = counter.most_common(1)[0][0]
        return str(most_common_answer)

    def _extract_number(self, text: str):
        """Extract the final numerical answer from solver output."""
        # Pattern 1: "#### 42" or "#### 42.5"
        match = re.search(r'####\s*(\d+(?:\.\d+)?)', text)
        if match:
            return float(match.group(1))

        # Pattern 2: "The answer is 42"
        match = re.search(r'[Tt]he answer is\s*(\d+(?:\.\d+)?)', text)
        if match:
            return float(match.group(1))

        # Pattern 3: last standalone number in the text
        numbers = re.findall(r'(?<![\d.])(\d+(?:\.\d+)?)(?![\d.])', text)
        if numbers:
            try:
                return float(numbers[-1])
            except (ValueError, IndexError):
                pass

        return None