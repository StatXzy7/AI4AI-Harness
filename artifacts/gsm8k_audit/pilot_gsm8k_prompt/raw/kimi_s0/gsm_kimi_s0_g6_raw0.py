"""Self-consistency with majority voting over diverse stochastic reasoning paths for GSM8K."""
from ..harness_base import MathHarness
import re
from collections import Counter


class GsmGsmKimiS0G6(MathHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Solve the following grade-school math problem step by step. "
            "Show your work clearly and end with '#### <number>'.\n\n"
            f"Problem: {question}\n\n"
            "Solution:"
        )

        # Generate multiple diverse reasoning paths with temperature > 0
        responses = self.llm(prompt, system="", temperature=0.7, n=5)

        # Normalize to list
        if isinstance(responses, str):
            responses = [responses]

        # Extract answers paired with response length (for tie-breaking)
        answer_length_pairs = []
        for resp in responses:
            ans = self._extract_answer(resp)
            if ans is not None:
                answer_length_pairs.append((ans, len(resp)))

        if not answer_length_pairs:
            # Fallback to greedy decoding
            greedy = self.llm(prompt, system="", temperature=0.0, n=1)
            if isinstance(greedy, list):
                greedy = greedy[0]
            ans = self._extract_answer(greedy)
            return ans if ans is not None else "0"

        # Majority vote with tie-breaking by cumulative response length
        answer_scores = Counter()
        answer_total_length = {}
        for ans, length in answer_length_pairs:
            answer_scores[ans] += 1
            answer_total_length[ans] = answer_total_length.get(ans, 0) + length

        best = sorted(
            answer_scores.keys(),
            key=lambda a: (answer_scores[a], answer_total_length[a]),
            reverse=True
        )[0]

        return best

    def _extract_answer(self, text: str) -> str | None:
        """Extract the final numerical answer from a response string."""
        # Pattern 1: #### <number>
        match = re.search(r'####\s*(-?\d+(?:\.\d+)?)', text)
        if match:
            return match.group(1)

        # Pattern 2: "The answer is X" or "answer: X"
        match = re.search(
            r'(?:the answer is|answer is|answer:)\s*(-?\d+(?:\.\d+)?)',
            text, re.IGNORECASE
        )
        if match:
            return match.group(1)

        # Pattern 3: last number in the text
        numbers = re.findall(r'-?\d+(?:\.\d+)?', text)
        if numbers:
            return numbers[-1]

        return None