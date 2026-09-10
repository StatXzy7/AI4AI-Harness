"""
Improvement mechanism: Ensemble with majority voting over multiple sampled solutions.
Generates 5 diverse solutions with temperature=0.7, then uses majority voting on
the final answer, falling back to single greedy generation on tie.
"""

from ..harness_base import MathHarness
from collections import Counter
import re

class GsmGsmKimiS0G2(MathHarness):
    def solve(self, question: str) -> str:
        """
        Solve using ensemble voting with fallback to single greedy generation.
        """
        # Generate multiple solutions with controlled diversity
        candidates = []
        for _ in range(5):
            response = self.llm(
                question,
                system="You are a mathematics solver. Solve step by step and end with #### <answer>.",
                temperature=0.7,
                n=1
            )
            answer = self._extract_final_answer(response)
            if answer:
                candidates.append(answer)
        
        # Use majority voting if we have candidates
        if candidates:
            counter = Counter(candidates)
            most_common, count = counter.most_common(1)[0]
            
            # If there's a clear majority, use it
            if count > 1:
                return most_common
        
        # Fallback to single greedy generation with deterministic temperature
        response = self.llm(
            question,
            system="You are a mathematics solver. Solve step by step and end with #### <answer>.",
            temperature=0.0,
            n=1
        )
        return self._extract_final_answer(response) or ""
    
    def _extract_final_answer(self, response: str) -> str:
        """Extract answer from #### line, supporting multiple formats."""
        if not response:
            return ""
        
        # Find the last line starting with ####
        lines = response.strip().split('\n')
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('####'):
                answer = line[4:].strip()
                # Clean up common formatting issues
                answer = answer.replace('**', '').strip()
                # Remove trailing period if present
                if answer.endswith('.'):
                    answer = answer[:-1]
                return answer
        
        # Fallback: look for answer patterns in last few lines
        for line in reversed(lines[-3:]):
            # Look for boxed answers: \boxed{...}
            boxed_match = re.search(r'\\boxed\{([^}]+)\}', line)
            if boxed_match:
                return boxed_match.group(1)
        
        return ""