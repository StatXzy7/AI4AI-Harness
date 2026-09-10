"""Two-step verification: generate a solution, verify it, and if incorrect, regenerate with higher temperature."""

from ..harness_base import MathHarness

class GsmGsmErnieS0G0(MathHarness):
    def solve(self, question: str) -> str:
        # First attempt with greedy generation (temperature=0)
        prompt = f"Solve the following math problem. Put your final answer on the last line in the form '#### <answer>'.\n\n{question}"
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        answer = self._extract_answer(response)
        
        # Verification step: ask the model to check the solution and answer
        verify_prompt = f"Check the following solution and answer. Is the answer correct? Respond with 'Correct' or 'Incorrect'.\n\nSolution:\n{response}\n\nAnswer: {answer}"
        verify_response = self.llm(verify_prompt, system="", temperature=0.0, n=1)
        
        if "Correct" in verify_response:
            return answer
        else:
            # Second attempt with higher temperature to encourage a different solution
            response2 = self.llm(prompt, system="", temperature=0.7, n=1)
            answer2 = self._extract_answer(response2)
            return answer2
    
    def _extract_answer(self, response: str) -> str:
        """Extract the answer from the last line starting with '#### '."""
        lines = response.strip().split('\n')
        for line in reversed(lines):
            if line.strip().startswith('#### '):
                return line.strip()[5:].strip()
        # Fallback: return the last line if no marker found
        return lines[-1].strip() if lines else ""