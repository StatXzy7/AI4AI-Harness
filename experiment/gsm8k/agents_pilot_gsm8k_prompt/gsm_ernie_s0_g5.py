"""Implements a generate-then-verify loop that re-prompts the solver to check its own answer, retrying with varied prompts if verification fails."""

from ..harness_base import MathHarness
import re


class GsmGsmErnieS0G5(MathHarness):
    def solve(self, question: str) -> str:
        # Try up to 3 attempts with different prompt phrasings
        prompt_variants = [
            f"Solve the following math problem step by step.\n\n{question}\n\nLet's think step by step.",
            f"Solve this grade school math problem carefully.\n\n{question}\n\nShow your work.",
            f"Work through this math problem.\n\n{question}\n\nExplain your reasoning.",
        ]

        for attempt in range(3):
            prompt = prompt_variants[attempt % len(prompt_variants)]
            raw = self.llm(prompt, system="", temperature=0.0, n=1)

            # Extract the numeric answer from the raw output
            answer = self._extract_answer(raw)
            if answer is None:
                continue

            # Verify: ask the solver to confirm the answer is correct
            verify_prompt = (
                f"A student solved this problem:\n\n{question}\n\n"
                f"Their final answer was: {answer}\n\n"
                f"Is this answer correct? Reply with 'Yes' or 'No' only."
            )
            verdict = self.llm(verify_prompt, system="", temperature=0.0, n=1).strip().lower()

            if verdict.startswith("yes"):
                return answer

        # If all attempts fail verification, fall back to the last extracted answer
        return answer if answer is not None else "0"

    def _extract_answer(self, text: str) -> str:
        # Try common answer formats: "#### 42", "The answer is 42", "Answer: 42", etc.
        patterns = [
            r"####\s*(\-?\d+(?:\.\d+)?)",
            r"[Tt]he answer is\s*(\-?\d+(?:\.\d+)?)",
            r"[Aa]nswer\s*[:=]\s*(\-?\d+(?:\.\d+)?)",
            r"(\-?\d+(?:\.\d+)?)\s*$",  # last number on a line
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                return m.group(1)
        return None