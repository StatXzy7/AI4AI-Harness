"""Improvement: multi-sample self-consistency with answer verification and fallback generation."""
from ..harness_base import MathHarness
from collections import Counter
from typing import List, Optional, Tuple
import re

class GsmGsmKimiS0G1(MathHarness):
    """
    Harness implementing self-consistency with multiple sampling, answer extraction,
    and verification via secondary generation for ambiguous cases.
    """
    
    def solve(self, question: str) -> str:
        """
        Generate multiple solution attempts, extract answers, select most consistent
        answer with verification and fallback strategies.
        """
        # System prompt for primary solutions
        system_prompt = (
            "You are an expert mathematician solving competition problems. "
            "Solve the problem step by step, showing clear reasoning. "
            "At the end, put ONLY the final answer on a new line in the format '#### <answer>'. "
            "The answer should be a number, fraction, expression, or set as appropriate."
        )
        
        # Generate multiple solution attempts with moderate temperature for diversity
        n_samples = 5
        solutions: List[str] = []
        for _ in range(n_samples):
            response = self.llm(
                prompt=question,
                system=system_prompt,
                temperature=0.3,  # Moderate temperature for diversity
                n=1
            )
            if response and isinstance(response, str):
                solutions.append(response)
        
        # Extract answers from all solutions
        extracted_answers: List[str] = []
        for sol in solutions:
            answer = self._extract_final_answer(sol)
            if answer:
                extracted_answers.append(answer)
        
        # If we have at least one answer, proceed to selection
        if extracted_answers:
            answer_counts = Counter(extracted_answers)
            most_common_answer, count = answer_counts.most_common(1)[0]
            
            # If we have a clear majority (more than half), return it
            if count > len(extracted_answers) / 2:
                return most_common_answer
            
            # If no clear majority but we have multiple distinct answers, try verification
            if len(answer_counts) > 1:
                verified_answer = self._verify_answer(question, extracted_answers)
                if verified_answer:
                    return verified_answer
        
        # Fallback: generate with higher creativity if initial attempts failed
        fallback_system = (
            "You are solving a math competition problem. Try multiple approaches: "
            "algebraic manipulation, substitution, or pattern recognition. "
            "Final answer must be on last line as '#### <answer>'."
        )
        response = self.llm(
            prompt=f"Find all possible solutions to this problem: {question}",
            system=fallback_system,
            temperature=0.6,  # Higher temperature for diversity
            n=1
        )
        
        if response and isinstance(response, str):
            fallback_answer = self._extract_final_answer(response)
            if fallback_answer:
                return fallback_answer
        
        # Last resort: return most common from initial attempts
        if extracted_answers:
            return Counter(extracted_answers).most_common(1)[0][0]
        
        # If all else fails, return empty string
        return ""
    
    def _extract_final_answer(self, text: str) -> Optional[str]:
        """Extract answer from the '#### <answer>' pattern in solver output."""
        if not text:
            return None
        
        # Look for the pattern on the last line
        lines = text.strip().split('\n')
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('####'):
                answer_part = line[4:].strip()
                if answer_part:
                    return answer_part
        
        # Fallback: look for any line with #### pattern
        for line in lines:
            line = line.strip()
            if '####' in line:
                match = re.search(r'####\s*(.+)$', line)
                if match:
                    return match.group(1).strip()
        
        return None
    
    def _verify_answer(self, question: str, candidate_answers: List[str]) -> Optional[str]:
        """
        Use the solver to verify candidate answers by asking which is correct.
        """
        if len(candidate_answers) < 2:
            return None
        
        # Create verification prompt
        verification_prompt = (
            f"I have a math problem: {question}\n\n"
            f"I computed several potential answers: {candidate_answers}\n\n"
            "Please verify which answer is correct by considering the problem carefully. "
            "Provide ONLY the correct answer on the last line in format '#### <answer>'."
        )
        
        response = self.llm(
            prompt=verification_prompt,
            system="You are a careful mathematician verifying solutions. Choose the correct answer.",
            temperature=0.1,  # Low temperature for consistency
            n=1
        )
        
        if response and isinstance(response, str):
            verified = self._extract_final_answer(response)
            if verified and verified in candidate_answers:
                return verified
        
        return None