"""Multi-pass solve-and-verify harness: solves, then asks the solver to verify by working backwards, re-solving if inconsistent."""
from ..harness_base import MathHarness
import re


class GsmGsmKimiS0G0(MathHarness):
    def _extract_answer(self, text: str) -> str | None:
        """Extract the final numeric answer from solver output."""
        # Prefer the #### pattern
        m = re.search(r'####\s*(-?\d[\d,\.]*)\s*$', text, re.MULTILINE)
        if m:
            return m.group(1).replace(',', '').strip()
        # Then "the answer is X" style
        m = re.search(r'(?:the\s+answer\s+is|answer\s*[:=]|final\s+answer)\s*(-?\d[\d,\.]*)', text, re.IGNORECASE)
        if m:
            return m.group(1).replace(',', '').strip()
        # Fallback: last number in the text
        numbers = re.findall(r'-?\d[\d,\.]*', text)
        if numbers:
            return numbers[-1].replace(',', '').strip()
        return None

    def solve(self, question: str) -> str:
        # --- Pass 1: Initial solve ---
        solve_prompt = (
            f"Solve the following grade-school math problem step by step. "
            f"End your answer with a line in the format: #### <number>\n\n"
            f"Question: {question}"
        )
        solution = self.llm(solve_prompt, system="", temperature=0.0, n=1)
        answer = self._extract_answer(solution)

        if answer is None:
            return ""

        # --- Pass 2: Verification by working backwards ---
        verify_prompt = (
            f"Problem: {question}\n\n"
            f"Proposed answer: {answer}\n\n"
            f"Please verify this answer by working backwards: substitute the answer back into the problem "
            f"and check whether it satisfies all the conditions stated. "
            f"If the answer is correct, respond with: VERIFIED\n"
            f"If the answer is incorrect, provide the correct answer and end with: #### <correct_number>"
        )
        verification = self.llm(verify_prompt, system="", temperature=0.0, n=1)

        if "VERIFIED" in verification.upper():
            return answer

        # Try to extract a corrected answer from the verification pass
        corrected = self._extract_answer(verification)
        if corrected is not None and corrected != answer:
            return corrected

        # --- Pass 3: Re-solve with verification feedback as context ---
        resolve_prompt = (
            f"Solve the following grade-school math problem step by step. "
            f"End your answer with a line in the format: #### <number>\n\n"
            f"Question: {question}\n\n"
            f"Note: A previous attempt gave the answer {answer}, but verification suggested it might be incorrect. "
            f"Please carefully re-solve the problem from scratch."
        )
        retry = self.llm(resolve_prompt, system="", temperature=0.0, n=1)
        retry_answer = self._extract_answer(retry)

        if retry_answer is not None:
            return retry_answer

        return answer  # Fall back to original answer