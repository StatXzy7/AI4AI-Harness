"""
Uses dual-path verification with prompt-specialized sampling and majority-vote adjudication for math problem solving.
"""
from collections import Counter
import re
from ..harness_base import MathHarness

class GsmGsmKimiS0G7(MathHarness):
    def solve(self, question: str) -> str:
        """Solve using dual-path verification with specialized prompt sampling."""
        
        # Extract answer from solver output (handles '####' format)
        def extract_answer(text: str) -> str:
            if '####' in text:
                answer = text.split('####')[-1].strip()
            else:
                # Fallback: try to find last line with potential math answer
                lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
                if lines:
                    answer = lines[-1]
                else:
                    answer = text.strip()
            return self._normalize_answer(answer)
        
        def _normalize_answer(self, ans: str) -> str:
            """Normalize answer string for comparison."""
            # Remove common formatting variations
            ans = ans.replace(' ', '').replace(',', '')
            # Normalize fraction notation
            ans = ans.replace('\\frac{', '').replace('}{', '/').replace('}', '')
            # Normalize decimals vs fractions? Keep as-is for now
            return ans
        
        # Path 1: Standard CoT prompt
        prompt_cot = f"""You are a math problem solver. Solve step-by-step then give final answer.

Problem: {question}

Solution: Let me solve this step by step.
"""
        response_cot = self.llm(prompt_cot, system="", temperature=0.0, n=1)
        answer_cot = extract_answer(response_cot[0] if isinstance(response_cot, list) else response_cot)
        
        # Path 2: Direct verification prompt (asks for answer directly, no steps)
        prompt_direct = f"""Provide ONLY the final answer to this math problem. No explanation.

Problem: {question}

Answer: """
        response_direct = self.llm(prompt_direct, system="", temperature=0.0, n=1)
        answer_direct = extract_answer(response_direct[0] if isinstance(response_direct, list) else response_direct)
        
        # Path 3: Final verification with problem + both candidate answers
        prompt_verify = f"""Math problem: {question}

Candidate answers:
1) {answer_cot}
2) {answer_direct}

Which answer is more likely correct? Reply with ONLY the better answer number (1 or 2).
"""
        response_verify = self.llm(prompt_verify, system="", temperature=0.0, n=1)
        verify_text = response_verify[0] if isinstance(response_verify, list) else response_verify
        
        # Parse verification response
        match = re.search(r'[12]', verify_text)
        if match:
            choice = int(match.group())
            if choice == 1:
                return answer_cot
            else:
                return answer_direct
        else:
            # Fallback: if verification fails, use majority logic or default
            # Simple heuristic: if answers are similar, return either; else return CoT
            if _normalize_answer(answer_cot) == _normalize_answer(answer_direct):
                return answer_cot
            else:
                return answer_cot  # Default to CoT path