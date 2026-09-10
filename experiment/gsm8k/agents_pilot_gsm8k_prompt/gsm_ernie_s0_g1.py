"""Uses self-consistency by generating three independently prompted solutions and returning the most frequent numerical answer."""

from ..harness_base import MathHarness
import re
from collections import Counter


class GsmGsmErnieS0G1(MathHarness):
    def solve(self, question: str) -> str:
        # Self-consistency: generate 3 solutions with slightly varied prompt prefixes,
        # extract the numeric answer from each, and return the mode.
        prompt_variants = [
            f"Solve the following grade-school math problem. Show your work.\n\n{question}\n\nAnswer:",
            f"Let's work through this step by step.\n\n{question}\n\nThe answer is",
            f"Calculate the result carefully.\n\n{question}\n\nResult:",
        ]

        answers = []
        for prompt in prompt_variants:
            raw = self.llm(prompt, system="", temperature=0.0, n=1)
            num = self._extract_number(raw)
            if num is not None:
                answers.append(num)

        if not answers:
            # Fallback: try one more extraction on the first variant
            raw = self.llm(prompt_variants[0], system="", temperature=0.0, n=1)
            num = self._extract_number(raw)
            return str(num) if num is not None else ""

        # Return the most common answer (mode)
        mode_answer = Counter(answers).most_common(1)[0][0]
        return str(mode_answer)

    def _extract_number(self, text: str) -> int | None:
        """Extract the final numerical answer from solver output."""
        # Look for "#### <number>" pattern first
        m = re.search(r"####\s*(\-?\d+(?:\.\d+)?)", text)
        if m:
            return int(float(m.group(1)))

        # Look for "The answer is <number>" or similar
        m = re.search(r"(?:answer|result|is)\s*[:=]?\s*(\-?\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if m:
            return int(float(m.group(1)))

        # Look for last standalone number in the text
        numbers = re.findall(r"(?<!\d)(\-?\d+(?:\.\d+)?)(?!\d)", text)
        if numbers:
            return int(float(numbers[-1]))

        return None