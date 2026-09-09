"""Uses self-consistency by generating multiple solutions with varied prompts and selecting the most frequent answer."""
from ..harness_base import MathHarness
import re
from collections import Counter

class GsmGsmErnieS0G3(MathHarness):
    """Harness that applies self-consistency over a frozen GSM8K solver by using multiple prompt variations."""
    
    def _extract_answer(self, text: str) -> str:
        """Extract the final numeric answer from the solver's output using known patterns."""
        patterns = [
            r'####\s*(\d+(?:\.\d+)?)',
            r'The answer is\s*(\d+(?:\.\d+)?)',
            r'Answer:\s*(\d+(?:\.\d+)?)',
            r'Final answer:\s*(\d+(?:\.\d+)?)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        # Fallback: take the last number in the last line of the response
        lines = text.strip().split('\n')
        if lines:
            last_line = lines[-1]
            numbers = re.findall(r'\d+(?:\.\d+)?', last_line)
            if numbers:
                return numbers[-1]
        # Ultimate fallback: first number found anywhere
        numbers = re.findall(r'\d+(?:\.\d+)?', text)
        return numbers[0] if numbers else ""

    def solve(self, question: str) -> str:
        """Generate multiple answers via varied prompts and return the most frequent one."""
        prompt_templates = [
            "Question: {question}\nAnswer:",
            "Solve the following problem: {question}\nAnswer:",
            "Let's think step by step. {question}\nAnswer:",
            "I need help solving this: {question}\nAnswer:",
            "Please solve: {question}\nAnswer:"
        ]
        
        answers = []
        for template in prompt_templates:
            prompt = template.format(question=question)
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            answer = self._extract_answer(response)
            if answer:
                answers.append(answer)
        
        if not answers:
            # If extraction fails entirely, return empty string (should rarely happen)
            return ""
        
        # Select the most common answer; break ties by first occurrence
        counter = Counter(answers)
        most_common = counter.most_common(1)[0][0]
        return most_common