"""Uses best-of-3 self-consistency with answer verification: generates three independent solutions, verifies each answer against the problem, and returns the most frequently verified answer."""

from ..harness_base import MathHarness
import re


class GsmGsmErnieS0G2(MathHarness):
    def solve(self, question: str) -> str:
        # Best-of-3 self-consistency with per-answer verification
        verified_answers = []

        for attempt in range(3):
            # Phase 1: Generate a detailed solution
            solve_prompt = (
                f"Solve the following math problem step by step. "
                f"Show all your reasoning clearly. "
                f"Put your final answer on the last line in the form '#### <answer>'.\n\n"
                f"Problem: {question}"
            )
            raw = self.llm(solve_prompt, system="", temperature=0.7, n=1)

            # Extract the answer from the last line
            answer = self._extract_answer(raw)
            if answer is None:
                continue

            # Phase 2: Verify the extracted answer against the problem
            verify_prompt = (
                f"A student solved this problem and got the answer: {answer}\n\n"
                f"Problem: {question}\n\n"
                f"Is this answer correct? Respond with only 'YES' or 'NO'. "
                f"If NO, briefly state what the correct answer should be."
            )
            verdict = self.llm(verify_prompt, system="", temperature=0.0, n=1).strip().upper()

            if verdict.startswith("YES"):
                verified_answers.append(answer)

        # Phase 3: Pick the most common verified answer (or first if tie/none)
        if verified_answers:
            # Count frequencies
            freq = {}
            for a in verified_answers:
                freq[a] = freq.get(a, 0) + 1
            best = max(freq, key=freq.get)
            return best

        # Fallback: if no answer verified, return the most common raw answer
        all_answers = []
        for attempt in range(3):
            solve_prompt = (
                f"Solve the following math problem step by step. "
                f"Show all your reasoning clearly. "
                f"Put your final answer on the last line in the form '#### <answer>'.\n\n"
                f"Problem: {question}"
            )
            raw = self.llm(solve_prompt, system="", temperature=0.7, n=1)
            answer = self._extract_answer(raw)
            if answer is not None:
                all_answers.append(answer)

        if all_answers:
            freq = {}
            for a in all_answers:
                freq[a] = freq.get(a, 0) + 1
            return max(freq, key=freq.get)

        # Last resort: single greedy call
        solve_prompt = (
            f"Solve the following math problem step by step. "
            f"Put your final answer on the last line in the form '#### <answer>'.\n\n"
            f"Problem: {question}"
        )
        raw = self.llm(solve_prompt, system="", temperature=0.0, n=1)
        return self._extract_answer(raw) or "0"

    def _extract_answer(self, text: str) -> str:
        """Extract the answer from a line ending with '#### <answer>'."""
        lines = text.strip().split("\n")
        for line in reversed(lines):
            match = re.search(r"####\s*(.+)", line)
            if match:
                return match.group(1).strip()
        return None