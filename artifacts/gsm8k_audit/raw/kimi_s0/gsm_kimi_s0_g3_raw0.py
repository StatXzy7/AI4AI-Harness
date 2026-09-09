"""Diverse prompt ensemble with majority voting and meta-reconciliation fallback for GSM8K."""
from ..harness_base import MathHarness
import re
from collections import Counter


class GsmGsmKimiS0G3(MathHarness):
    def solve(self, question: str) -> str:
        # Three diverse prompt templates that trigger different reasoning styles
        prompts = [
            f"Solve the following math problem step by step. Show your work clearly and end with #### <answer>.\n\n{question}",
            f"Read this problem carefully. Break it into steps, solve each step, and verify your reasoning. End with #### <answer>.\n\n{question}",
            f"Solve this problem by first identifying the key quantities and operations needed. Then compute step by step. End with #### <answer>.\n\n{question}",
        ]

        solutions = []
        answers = []

        for prompt in prompts:
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            solutions.append(response)
            ans = self._extract_number(response)
            answers.append(ans)

        # Majority vote among extracted answers
        counter = Counter(answers)
        best_answer, count = counter.most_common(1)[0]

        if count >= 2 and best_answer:
            return best_answer

        # No consensus: meta-reconciliation step
        combined = "\n\n---\n\n".join(
            f"Solution {chr(65 + i)}:\n{sol}" for i, sol in enumerate(solutions)
        )
        meta_prompt = (
            f"Three different solution attempts are shown below for the same problem. "
            f"Analyze them for correctness and output ONLY the correct numerical answer.\n\n"
            f"Problem: {question}\n\n{combined}\n\nCorrect answer:"
        )
        meta_response = self.llm(meta_prompt, system="", temperature=0.0, n=1)
        meta_answer = self._extract_number(meta_response)

        return meta_answer if meta_answer else (best_answer if best_answer else answers[0])

    def _extract_number(self, text: str) -> str:
        """Extract the final numerical answer from solver text."""
        # Primary: #### pattern (GSM8K standard)
        match = re.search(r"####\s*(-?\d[\d,]*\.?\d*)", text)
        if match:
            return match.group(1).replace(",", "")

        # Secondary: "answer is X" pattern
        match = re.search(
            r"(?:the\s+)?answer\s+(?:is|=)\s*(-?\d[\d,]*\.?\d*)", text, re.IGNORECASE
        )
        if match:
            return match.group(1).replace(",", "")

        # Tertiary: last number in text
        numbers = re.findall(r"-?\d[\d,]*\.?\d*", text)
        if numbers:
            return numbers[-1].replace(",", "")

        return ""