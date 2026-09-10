"""Uses self-consistency with multiple sampling and majority voting to improve reliability of weak solver."""
import re
from collections import Counter
from typing import List

class GsmGsmKimiS0G5(MathHarness):
    def solve(self, question: str) -> str:
        """
        Improved solving mechanism using self-consistency:
        1. Generate N diverse solutions via temperature sampling
        2. Extract answers from each solution's final '####' line
        3. Vote for most frequent answer (majority voting)
        4. If no majority, fallback to greedy generation
        """
        # Generate 5 diverse solutions with moderate temperature for sampling
        solutions = self.llm(
            prompt=question,
            system=self._build_system_prompt(),
            temperature=0.7,
            n=5
        )
        
        # Extract answers from each solution
        extracted_answers = []
        for solution in solutions:
            answer = self._extract_answer(solution)
            if answer:
                extracted_answers.append(answer)
        
        # If we have answers, use majority voting
        if extracted_answers:
            answer_counts = Counter(extracted_answers)
            most_common_answer, count = answer_counts.most_common(1)[0]
            
            # Require at least 2 votes for consistency, otherwise fallback
            if count >= 2:
                return most_common_answer
        
        # Fallback: Single greedy generation (highest confidence)
        greedy_solution = self.llm(
            prompt=question,
            system=self._build_system_prompt(),
            temperature=0.0,
            n=1
        )[0]
        
        fallback_answer = self._extract_answer(greedy_solution)
        return fallback_answer if fallback_answer else ""
    
    def _build_system_prompt(self) -> str:
        """System prompt that enforces answer format and chain-of-thought."""
        return (
            "You are a precise mathematical problem solver. Solve the given competition-math problem "
            "step by step. After your final answer, ALWAYS write the answer on a new line in the format:\n"
            "#### <answer>\n"
            "Where <answer> is the final answer in simplest form (number, fraction, LaTeX expression, "
            "interval, or tuple). Do not include any text after the #### line."
        )
    
    def _extract_answer(self, text: str) -> str:
        """Extract answer from the #### line with robust pattern matching."""
        # Look for the #### marker followed by answer
        match = re.search(r'####\s*(.+?)(?:\s*$)', text, re.MULTILINE)
        if match:
            answer = match.group(1).strip()
            # Clean up common artifacts
            answer = self._clean_answer(answer)
            return answer
        
        # Fallback: Look for final mathematical expression if #### missing
        patterns = [
            r'(?:final answer|answer)\s*(?:is|=|:)\s*(.+?)(?:\s*$)',
            r'(?:boxed|\\boxed)\{(.+?)\}',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                answer = match.group(1).strip()
                answer = self._clean_answer(answer)
                if answer:
                    return answer
        
        return ""
    
    def _clean_answer(self, answer: str) -> str:
        """Clean answer string of common formatting issues."""
        # Remove trailing punctuation except mathematical notation
        answer = re.sub(r'[.!?]+$', '', answer).strip()
        
        # Remove common prefixes like "the answer is"
        answer = re.sub(r'^(?:the answer is|answer:|final answer:|result:)\s*', '', answer, flags=re.IGNORECASE)
        
        # Normalize LaTeX formatting
        answer = answer.replace('\\ ', ' ')
        answer = re.sub(r'\s+', ' ', answer).strip()
        
        return answer