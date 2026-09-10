"""Improve accuracy by generating multiple responses and selecting the most consistent answer via majority voting."""
from ..harness_base import MathHarness
import re
from collections import Counter

class GsmGsmKimiS0G5(MathHarness):
    def _extract_final_answer(self, text: str) -> str:
        """Extract the final numerical answer from solver output."""
        # Try "#### number" pattern first
        match = re.search(r'####\s*([\d,]+)', text)
        if match:
            return match.group(1).replace(',', '')
        
        # Try "The answer is number" pattern
        match = re.search(r'The answer is\s*([\d,]+)', text)
        if match:
            return match.group(1).replace(',', '')
        
        # Fallback: find last number in the text
        numbers = re.findall(r'[\d,]+', text)
        if numbers:
            return numbers[-1].replace(',', '')
        
        return ""

    def solve(self, question: str) -> str:
        """Generate multiple responses and use majority voting to select the most consistent answer."""
        num_samples = 5
        answers = []
        
        for _ in range(num_samples):
            response = self.llm(question, system="", temperature=0.7, n=1)
            answer = self._extract_final_answer(response)
            if answer:
                answers.append(answer)
        
        if not answers:
            return ""
        
        # Count answer frequencies and return the most common
        counter = Counter(answers)
        most_common_answer, count = counter.most_common(1)[0]
        
        # If all answers are different, fall back to the last response
        if count == 1 and len(answers) > 1:
            return answers[-1]
        
        return most_common_answer