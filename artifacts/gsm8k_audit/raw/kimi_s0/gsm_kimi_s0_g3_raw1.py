import re
from collections import Counter
from ..harness_base import MathHarness


class GsmGsmKimiS0G3(MathHarness):
    """Self-consistency sampling with answer voting and fallback extraction for math problems."""
    
    def solve(self, question: str) -> str:
        # Generate multiple candidate solutions via sampling
        n_samples = 5
        candidates = []
        prompt = (
            "Solve the following math problem step by step. Show your work, "
            "and put your final answer on the last line in the exact format: '#### <answer>'\n\n"
            f"Problem: {question}"
        )
        
        # Generate multiple solutions with temperature > 0 to get diversity
        responses = self.llm(
            prompt,
            system="You are a mathematics problem solver. Provide detailed solutions and end with '#### <answer>'.",
            temperature=0.7,
            n=n_samples
        )
        
        # Extract answers from each candidate solution
        extracted_answers = []
        for response in responses:
            answer = self._extract_answer(response)
            if answer:
                extracted_answers.append(answer)
        
        if not extracted_answers:
            # Fallback: use the last line of first response as answer
            return self._extract_fallback(responses[0] if responses else "")
        
        # Majority voting among extracted answers
        if extracted_answers:
            most_common = Counter(extracted_answers).most_common(1)[0][0]
            return most_common
        
        return ""
    
    def _extract_answer(self, text: str) -> str:
        """Extract answer from the '#### <answer>' pattern at the end of text."""
        # Look for the pattern in the last few lines
        lines = text.strip().split('\n')
        # Search from the end for the pattern
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('####'):
                answer_part = line[4:].strip()
                if answer_part:
                    return answer_part
        
        # Fallback: look for common answer patterns
        patterns = [
            r'\\boxed{(.+?)}',
            r'\\frac{(.+?)}{(.+?)}',
            r'(\d+(?:\.\d+)?)',
            r'(\d+/\d+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                # Return the last match (usually the final answer)
                if pattern.startswith(r'\\frac'):
                    numerator, denominator = matches[-1]
                    return f"\\frac{{{numerator}}}{{{denominator}}}"
                return matches[-1]
        
        return ""
    
    def _extract_fallback(self, text: str) -> str:
        """Fallback extraction when no #### pattern is found."""
        lines = text.strip().split('\n')
        if not lines:
            return ""
        
        # Try to get the last non-empty line
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith('#'):
                # Clean common answer markers
                line = re.sub(r'^(Answer|Final answer|The answer is)[:\s]*', '', line, flags=re.IGNORECASE)
                line = line.strip('. ')
                if line:
                    return line
        
        return ""