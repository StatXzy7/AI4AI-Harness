"""Improve single greedy generation by using a majority voting mechanism with multiple independent solutions."""
from ..harness_base import MathHarness
import re
from collections import Counter


class GsmGsmKimiS0G7(MathHarness):
    def _extract_final_answer(self, solution_text: str) -> str:
        """Extract the answer following '####' from a solution."""
        lines = solution_text.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("####"):
                return line[4:].strip()
        # Fallback: try to find answer pattern at end of text
        match = re.search(r"####\s*(.+?)$", solution_text, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return ""

    def _generate_one_solution(self, question: str) -> str:
        """Generate a single solution with step-by-step reasoning."""
        prompt = f"""Solve the following math problem step by step. Show all your work clearly, then provide your final answer on the last line in the format '#### <answer>'.

Problem: {question}

Solution:"""
        response = self.llm(prompt, system="You are a helpful math tutor.", temperature=0.7, n=1)
        return response[0] if response else ""

    def solve(self, question: str) -> str:
        """Generate multiple solutions and return the majority answer."""
        n_attempts = 5  # Generate 5 independent solutions
        answers = []
        
        # Collect multiple solutions
        for _ in range(n_attempts):
            solution = self._generate_one_solution(question)
            answer = self._extract_final_answer(solution)
            if answer:
                answers.append(answer)
        
        # If no answers extracted, fall back to single greedy generation
        if not answers:
            solution = self._generate_one_solution(question)
            return self._extract_final_answer(solution)
        
        # Use majority voting on extracted answers
        # Normalize answers for comparison (strip whitespace, lowercase for text comparison)
        normalized = [ans.strip().lower() for ans in answers]
        counter = Counter(normalized)
        most_common, count = counter.most_common(1)[0]
        
        # Return the original format of the most common answer
        for ans in answers:
            if ans.strip().lower() == most_common:
                return ans
        
        return answers[0]  # Should never reach here