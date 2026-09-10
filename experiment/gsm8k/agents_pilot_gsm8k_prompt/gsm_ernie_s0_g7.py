"""Uses self-consistency by generating multiple independent solutions with temperature > 0 and returning the majority vote answer."""

from ..harness_base import MathHarness
import re
from collections import Counter


class GsmGsmErnieS0G7(MathHarness):
    def solve(self, question: str) -> str:
        # Self-consistency: generate N diverse solutions and take the majority answer
        num_samples = 5
        answers = []

        for _ in range(num_samples):
            prompt = f"Question: {question}\n\nSolve step by step and give the final numerical answer."
            response = self.llm(prompt, system="", temperature=0.7, n=1)
            answer = self._extract_answer(response)
            if answer is not None:
                answers.append(answer)

        # If we got enough valid answers, return the most common one
        if len(answers) >= 3:
            majority = Counter(answers).most_common(1)[0][0]
            return str(majority)

        # Fallback: try a single greedy call if too few samples succeeded
        prompt = f"Question: {question}\n\nSolve step by step and give the final numerical answer."
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        answer = self._extract_answer(response)
        return str(answer) if answer is not None else "0"

    def _extract_answer(self, text: str):
        # Pattern 1: "#### 42"
        match = re.search(r"####\s*(\d+(?:\.\d+)?)", text)
        if match:
            return match.group(1)
        # Pattern 2: "The answer is 42"
        match = re.search(r"[Tt]he answer is\s*(\d+(?:\.\d+)?)", text)
        if match:
            return match.group(1)
        # Pattern 3: last standalone number in the text
        numbers = re.findall(r"(\d+(?:\.\d+)?)", text)
        if numbers:
            return numbers[-1]
        return None