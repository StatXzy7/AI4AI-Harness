"""Harness implementing majority voting with confidence-weighted answer aggregation."""
from ..harness_base import MathHarness
from collections import Counter
import re

class GsmGsmKimiS0G6(MathHarness):
    def _extract_answer(self, text: str) -> str:
        """Extract final answer from solver output after '####'."""
        if "####" in text:
            parts = text.split("####")
            answer_part = parts[-1].strip()
            # Take first line of the answer part
            answer_lines = [line.strip() for line in answer_part.split('\n') if line.strip()]
            if answer_lines:
                return answer_lines[0]
        # Fallback: use last non-empty line
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if lines:
            return lines[-1]
        return ""

    def _normalize_answer(self, answer: str) -> str:
        """Normalize answer string for comparison."""
        # Remove common formatting variations
        answer = answer.replace(" ", "")
        answer = answer.replace("\\,", "")
        answer = answer.replace("\\;", "")
        # Normalize fractions
        if "\\frac" in answer:
            answer = answer.replace("\\frac", "")
            answer = answer.replace("{", "(")
            answer = answer.replace("}", ")")
        # Normalize complex numbers
        answer = answer.replace("\\times", "*")
        # Remove trailing periods
        answer = answer.rstrip(".")
        return answer

    def solve(self, question: str) -> str:
        """Majority voting with 5 independent samples and normalized answer comparison."""
        # System prompt ensuring consistent answer format
        system = """You are a math problem solver. For each problem:
1. Provide a step-by-step solution.
2. Put your FINAL answer on the LAST LINE in the format: #### <answer>
Answer must be compact: number, fraction, LaTeX expression, interval, or tuple."""

        num_samples = 5
        answers = []
        confidence = []

        # Generate multiple solutions with different sampling
        for i in range(num_samples):
            # Vary temperature slightly for diversity (0.1 to 0.5)
            temp = 0.1 + (i * 0.1)
            response = self.llm(
                prompt=question,
                system=system,
                temperature=temp,
                n=1
            )
            
            # Extract and normalize answer
            raw_answer = self._extract_answer(response)
            normalized = self._normalize_answer(raw_answer)
            
            if normalized:
                answers.append(normalized)
                # Simple confidence heuristic: longer solutions get slight boost
                confidence.append(len(response.split('\n')))
        
        if not answers:
            return "No valid answer generated"

        # Majority voting with confidence weighting
        answer_counts = Counter(answers)
        max_count = max(answer_counts.values())
        
        # Get candidates with max votes
        candidates = [ans for ans, count in answer_counts.items() 
                     if count == max_count]
        
        if len(candidates) == 1:
            return candidates[0]
        
        # Tie-break using confidence (solution length)
        candidate_confidence = {}
        for cand in candidates:
            cand_conf = 0
            for ans, conf in zip(answers, confidence):
                if ans == cand:
                    cand_conf += conf
            candidate_confidence[cand] = cand_conf
        
        # Return candidate with highest total confidence
        return max(candidate_confidence.items(), key=lambda x: x[1])[0]