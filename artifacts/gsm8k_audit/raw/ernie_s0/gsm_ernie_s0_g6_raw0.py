"""This harness uses majority voting over three varied prompts to improve answer reliability for competition math problems."""

from ..harness_base import MathHarness


class GsmGsmErnieS0G6(MathHarness):
    def solve(self, question: str) -> str:
        # Three different prompt variations to encourage diverse reasoning
        prompts = [
            f"Solve the following math problem step by step. Put your final answer on the last line in the form '#### <answer>'.\n\n{question}",
            f"Solve this competition math problem using algebraic methods. Show your work. Final answer: '#### <answer>'.\n\n{question}",
            f"Solve the problem below. Think carefully. Final answer must be on the last line as '#### <answer>'.\n\n{question}",
        ]

        answers = []
        for prompt in prompts:
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            ans = self._extract_answer(response)
            answers.append(ans)

        # Majority voting: return the most frequent answer
        # In case of a tie, return the first one (from the first prompt)
        from collections import Counter
        counts = Counter(answers)
        most_common = counts.most_common(1)[0][0]
        return most_common

    def _extract_answer(self, response: str) -> str:
        """Extract the final answer from the solver's response.

        Looks for a line starting with '####' and returns the content after it.
        If not found, returns the last non-empty line as a fallback.
        """
        lines = response.strip().splitlines()
        # Search from the end for the '####' line
        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith('####'):
                return stripped[5:].strip()
        # Fallback: return the last non-empty line
        for line in reversed(lines):
            if line.strip():
                return line.strip()
        return ""