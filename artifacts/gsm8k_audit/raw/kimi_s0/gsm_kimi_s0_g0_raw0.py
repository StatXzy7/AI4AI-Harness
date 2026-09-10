"""GsmGsmKimiS0G0 harness that uses ensemble voting with verification for improved math problem solving."""
from collections import Counter
import re
import time
from ..harness_base import MathHarness


class GsmGsmKimiS0G0(MathHarness):
    """Improvement: Ensemble voting with answer normalization and verification.
    
    Mechanism: Generate multiple candidate solutions (with temperature sampling)
    instead of a single greedy generation. Normalize extracted answers (including
    fractions, intervals, expressions) and take majority vote. Add a verification
    step that re-derives answers if vote is split or confidence is low.
    """
    
    def __init__(self):
        super().__init__()
        self.num_samples = 5
        self.temperature = 0.3
        self.min_confidence_ratio = 0.6  # Minimum ratio for majority vote
        
    def normalize_answer(self, answer: str) -> str:
        """Normalize answer string to a canonical form for comparison."""
        # Remove whitespace and normalize
        answer = answer.strip()
        
        # Handle fractions - standardize format
        if '\\' in answer:  # LaTeX fractions like \frac{3}{4}
            # Extract numerator and denominator
            frac_pattern = r'\\frac\{(\d+)\}\{(\d+)\}'
            match = re.search(frac_pattern, answer)
            if match:
                num, den = match.groups()
                # Simplify fraction
                from math import gcd
                g = gcd(int(num), int(den))
                num, den = int(num)//g, int(den)//g
                if den == 1:
                    return str(num)
                elif den < 0:
                    return f"{-num}/{-den}"
                return f"{num}/{den}"
        
        if '/' in answer and answer.count('/') == 1:
            parts = answer.split('/')
            if len(parts) == 2 and all(p.strip().lstrip('-').isdigit() for p in parts):
                # Simple fraction - simplify
                from math import gcd
                num, den = int(parts[0].strip()), int(parts[1].strip())
                g = gcd(abs(num), abs(den))
                num, den = num//g, den//g
                if den == 1:
                    return str(num)
                elif den < 0:
                    return f"{-num}/{-den}"
                return f"{num}/{den}"
        
        # Handle intervals - standardize brackets
        interval_match = re.match(r'\((\d+),\s*(\d+)\)', answer)
        if interval_match:
            low, high = interval_match.groups()
            return f"({low},{high})"
        
        # Handle complex numbers
        if 'i' in answer:
            return answer.replace(' ', '')
        
        # Handle negative numbers
        if answer.startswith('-(') and answer.endswith(')'):
            inner = answer[2:-1]
            try:
                val = -eval(inner)
                return str(val)
            except:
                pass
        
        # Try to evaluate as numeric for comparison
        try:
            # For expressions like 2\sqrt{3}, we can't easily compare numerically
            # so keep as string
            if '\\' not in answer:
                val = eval(answer)
                if isinstance(val, float) and val.is_integer():
                    return str(int(val))
                elif isinstance(val, float):
                    # Round to avoid floating point issues
                    return f"{val:.6f}".rstrip('0').rstrip('.')
                return str(val)
        except:
            pass
        
        return answer
    
    def extract_final_answer(self, response: str) -> str:
        """Extract answer from the final line format '#### <answer>'."""
        lines = response.strip().split('\n')
        for line in reversed(lines):  # Start from last line
            line = line.strip()
            if line.startswith('####'):
                answer_part = line[4:].strip()
                if answer_part:
                    return self.normalize_answer(answer_part)
        
        # Fallback: look for common patterns
        for line in reversed(lines):
            line = line.strip()
            # Look for answers after "Answer:" or "answer:"
            if re.match(r'(?i)(?:answer|ans|result)[:\s]+', line):
                answer_part = re.sub(r'(?i)(?:answer|ans|result)[:\s]+', '', line).strip()
                if answer_part:
                    return self.normalize_answer(answer_part)
        
        return None
    
    def generate_solution(self, question: str, temperature: float = 0.0) -> str:
        """Generate a single solution with given temperature."""
        system_prompt = (
            "You are a precise math problem solver. Solve the following problem "
            "step by step. Show your work, then put your final answer on the "
            "last line in the exact format: #### <answer>\n"
            "The answer should be a number, fraction, or expression (e.g., 42, "
            "\\frac{3}{4}, 2\\sqrt{3}, (3,4], or a comma-separated list)."
        )
        
        response = self.llm(
            prompt=f"Problem: {question}",
            system=system_prompt,
            temperature=temperature,
            n=1
        )
        return response
    
    def verify_answer(self, question: str, candidate_answer: str) -> bool:
        """Verify answer by asking solver to check if it's correct."""
        verification_prompt = (
            f"Problem: {question}\n\n"
            f"Proposed answer: {candidate_answer}\n\n"
            "Please verify if this answer is correct by solving the problem "
            "independently. End your response with either 'VERIFIED: YES' or "
            "'VERIFIED: NO'."
        )
        
        response = self.llm(
            prompt=verification_prompt,
            system="You are a math answer verifier. Check if the proposed answer is correct.",
            temperature=0.0,
            n=1
        )
        
        # Check for verification result
        if 'VERIFIED: YES' in response.upper():
            return True
        return False
    
    def majority_vote(self, answers: list) -> str:
        """Perform majority vote on normalized answers."""
        if not answers:
            return None
        
        counter = Counter(answers)
        most_common = counter.most_common(1)[0]
        answer, count = most_common
        confidence = count / len(answers)
        
        if confidence >= self.min_confidence_ratio:
            return answer
        
        # If confidence is low, try to break tie
        if len(counter) == 2:
            # Try verifying both candidates
            for candidate_answer in counter.keys():
                if self.verify_answer(question, candidate_answer):
                    return candidate_answer
        
        # Fallback to most common even with low confidence
        return answer
    
    def solve(self, question: str) -> str:
        """Solve using ensemble voting with verification."""
        # Generate multiple candidate solutions
        candidate_solutions = []
        candidate_answers = []
        
        # First batch: temperature sampling
        for i in range(self.num_samples):
            temperature = self.temperature if i > 0 else 0.0
            solution = self.generate_solution(question, temperature)
            candidate_solutions.append(solution)
            
            answer = self.extract_final_answer(solution)
            if answer:
                candidate_answers.append(answer)
        
        # If we have enough answers, perform majority vote
        if len(candidate_answers) >= 3:
            final_answer = self.majority_vote(candidate_answers)
            if final_answer:
                return final_answer
        
        # Fallback: single greedy generation with verification
        solution = self.generate_solution(question, 0.0)
        answer = self.extract_final_answer(solution)
        
        if answer:
            # Try to verify
            if not self.verify_answer(question, answer):
                # Try one more time
                solution = self.generate_solution(question, 0.1)
                answer = self.extract_final_answer(solution)
                if answer and not self.verify_answer(question, answer):
                    # Last resort: return whatever we have
                    pass
        
        return answer or ""