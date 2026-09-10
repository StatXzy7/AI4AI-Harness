"""
Multi-prompt ensemble with majority voting: generates solutions using three distinct
prompting strategies, extracts numerical answers, and returns the majority vote,
falling back to a meta-adjudication prompt when no consensus exists.
"""

import re
from collections import Counter
from typing import List, Optional
from ..harness_base import MathHarness


class GsmGsmKimiS0G1(MathHarness):
    def solve(self, question: str) -> str:
        # Three distinct prompting strategies to elicit diverse reasoning paths
        prompts = [
            # Strategy 1: Standard chain-of-thought
            f"Solve this math problem step by step. End your answer with '#### <number>'.\n\nProblem: {question}",

            # Strategy 2: Structured with explicit intermediate calculations
            f"""Solve the following grade-school math problem. Show each calculation on its own line, labeling intermediate results clearly. End with '#### <number>'.

Problem: {question}""",

            # Strategy 3: Careful solving with built-in verification
            f"""Solve this math problem carefully. After finding your answer, double-check your work by re-reading the problem and verifying each step. End with '#### <number>'.

Problem: {question}""",
        ]

        answers: List[str] = []
        raw_responses: List[str] = []

        for prompt in prompts:
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            raw_responses.append(response)
            ans = self._extract_answer(response)
            if ans is not None:
                answers.append(ans)

        # Majority vote among extracted answers
        if answers:
            vote_counts = Counter(answers)
            most_common = vote_counts.most_common(1)[0]
            if most_common[1] >= 2:
                return most_common[0]

        # No clear majority: use meta-adjudication to pick the best answer
        combined = "\n\n---\n\n".join(
            [f"Attempt {i+1}:\n{r}" for i, r in enumerate(raw_responses)]
        )
        adjudication_prompt = f"""Three different solution attempts were made for this math problem. Review all three carefully, identify any errors in reasoning, and determine the correct final answer. Respond with ONLY the number.

Problem: {question}

{combined}

Correct answer (number only):"""

        final_response = self.llm(adjudication_prompt, system="", temperature=0.0, n=1)
        final_answer = self._extract_answer(final_response)

        if final_answer is not None:
            return final_answer

        # Last resort: return the first extracted answer or "0"
        return answers[0] if answers else "0"

    def _extract_answer(self, text: str) -> Optional[str]:
        """Extract the final numerical answer from the solver's response."""
        # Look for #### pattern (GSM8K standard format)
        match = re.search(r"####\s*(-?\d[\d,]*\.?\d*)", text)
        if match:
            return match.group(1).replace(",", "").strip()

        # Look for "The answer is X" or "answer is X"
        match = re.search(
            r"(?:the\s+)?answer\s+is\s+(-?\d[\d,]*\.?\d*)", text, re.IGNORECASE
        )
        if match:
            return match.group(1).replace(",", "").strip()

        # Look for the last number in the text as fallback
        numbers = re.findall(r"-?\d[\d,]*\.?\d*", text)
        if numbers:
            return numbers[-1].replace(",", "").strip()

        return None