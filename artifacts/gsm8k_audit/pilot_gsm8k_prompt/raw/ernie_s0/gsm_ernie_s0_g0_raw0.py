"""Uses self-consistency by generating multiple stochastic completions and returning the most frequent numerical answer."""

import re
from ..harness_base import MathHarness

class GsmGsmErnieS0G0(MathHarness):
    def solve(self, question: str) -> str:
        # Construct a standard prompt format for the frozen solver
        prompt = f"Question: {question}\nAnswer:"
        
        # Generate multiple completions with temperature > 0 for diversity
        completions = self.llm(prompt, system="", temperature=0.7, n=5)
        
        # Helper to extract the last numerical answer from a completion
        def extract_answer(text: str) -> str:
            # Find all numbers (integers or decimals) in the text
            numbers = re.findall(r'-?\d+\.?\d*', text)
            if not numbers:
                return ""
            # Return the last number found (typically the final answer)
            return numbers[-1].rstrip('.')  # remove trailing dot if present
        
        # Extract answers from all completions
        answers = [extract_answer(comp) for comp in completions]
        # Filter out empty strings (should not happen, but safe)
        answers = [a for a in answers if a]
        
        if not answers:
            # Fallback: try a single deterministic call if all extractions fail
            single = self.llm(prompt, system="", temperature=0.0, n=1)[0]
            return extract_answer(single)
        
        # Count frequencies and find the most common answer
        freq = {}
        for ans in answers:
            freq[ans] = freq.get(ans, 0) + 1
        
        # Determine the answer with the highest frequency; break ties by first occurrence
        max_freq = max(freq.values())
        for ans in answers:
            if freq[ans] == max_freq:
                return ans
        
        # Should never reach here, but return first answer as fallback
        return answers[0]