"""Uses self-consistency by generating multiple candidate solutions with varied prompts and returning the most frequent numerical answer."""

from ..harness_base import MathHarness
import re
from collections import Counter


class GsmGsmErnieS0G4(MathHarness):
    def solve(self, question: str) -> str:
        # Generate multiple candidate solutions with varied prompts for self-consistency
        num_samples = 5
        answers = []

        prompt_variations = [
            "{question}\n\nSolve this step by step. Show your work and put the final numerical answer on the last line.",
            "{question}\n\nLet's think through this carefully. Show all your work. End with the answer.",
            "{question}\n\nWork through this problem methodically. Display your reasoning then the final answer.",
            "{question}\n\nBreak this down step by step. Write out your full solution and box the final answer.",
            "{question}\n\nSolve this math problem showing each step clearly. State the final answer at the end.",
        ]

        for i in range(num_samples):
            prompt = prompt_variations[i].format(question=question)
            response = self.llm(prompt, system="", temperature=0.7, n=1)
            extracted = self._extract_answer(response)
            if extracted is not None:
                answers.append(extracted)

        # If we got at least one valid answer, return the most frequent (mode)
        if answers:
            vote_counts = Counter(answers)
            most_common = vote_counts.most_common(1)[0][0]
            return most_common

        # Fallback: single greedy generation if all extractions failed
        prompt = "{question}\n\nSolve this step by step. Put the final answer on the last line.".format(
            question=question
        )
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        extracted = self._extract_answer(response)
        if extracted is not None:
            return extracted

        return "0"

    def _extract_answer(self, text: str) -> str:
        """Extract the final numerical answer from the model's raw text output."""
        # Try "#### 42" format first (most reliable signal)
        match = re.search(r"####\s*(-?\d+(?:\.\d+)?)", text)
        if match:
            return match.group(1)

        # Try "The answer is 42" format
        match = re.search(r"[Tt]he answer is\s*(-?\d+(?:\.\d+)?)", text)
        if match:
            return match.group(1)

        # Try "Answer: 42" or "Answer: 42" format
        match = re.search(r"[Aa]nswer\s*[:=]\s*(-?\d+(?:\.\d+)?)", text)
        if match:
            return match.group(1)

        # Fallback: take the last standalone number in the text
        numbers = re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])", text)
        if numbers:
            return numbers[-1]

        return None