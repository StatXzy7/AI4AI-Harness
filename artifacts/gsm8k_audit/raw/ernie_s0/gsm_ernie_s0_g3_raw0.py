"""Generate an initial solution then verify/correct the extracted answer via a second LLM call with self-check prompt."""

from ..harness_base import MathHarness


class GsmGsmErnieS0G3(MathHarness):
    def solve(self, question: str) -> str:
        # First pass: generate a detailed solution with chain-of-thought
        solve_prompt = (
            f"Solve the following math problem step by step. "
            f"Show all your work and reasoning clearly. "
            f"Put your final answer on the last line in the form '#### <answer>'.\n\n"
            f"Problem: {question}"
        )
        first_output = self.llm(solve_prompt, system="", temperature=0.0, n=1)

        # Extract the answer from the first pass (last line starting with ####)
        first_answer = self._extract_answer(first_output)

        # Second pass: verify the extracted answer by asking the solver to self-check
        verify_prompt = (
            f"A student solved the following problem and got this answer: {first_answer}\n\n"
            f"Problem: {question}\n\n"
            f"Check whether this answer is correct. If it is correct, respond with "
            f"'CORRECT' followed by the same answer on the last line in the form '#### <answer>'. "
            f"If it is incorrect, solve the problem yourself step by step and put "
            f"your corrected final answer on the last line in the form '#### <answer>'."
        )
        second_output = self.llm(verify_prompt, system="", temperature=0.0, n=1)

        # Extract the final verified answer
        final_answer = self._extract_answer(second_output)
        return final_answer

    def _extract_answer(self, text: str) -> str:
        """Extract the answer from the last line starting with '####'."""
        lines = text.strip().split('\n')
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('####'):
                return line[5:].strip()
        # Fallback: return the whole text if no #### found
        return text.strip()