"""Uses self-consistency with multiple prompt variations and majority voting to improve answer reliability."""
from ..harness_base import MathHarness
from collections import Counter

class GsmGsmErnieS0G7(MathHarness):
    def solve(self, question: str) -> str:
        # Define multiple prompt variations to encourage diverse reasoning paths
        prompts = [
            f"Solve the following math problem. Put your final answer on the last line in the form '#### <answer>'.\n\n{question}",
            f"Solve this competition math problem step by step. Put your final answer on the last line in the form '#### <answer>'.\n\n{question}",
            f"This is a MATH-500 style problem. Solve it carefully and put your final answer on the last line in the form '#### <answer>'.\n\n{question}",
            f"Work through this math problem systematically. Put your final answer on the last line in the form '#### <answer>'.\n\n{question}",
            f"Solve the following problem using algebraic/geometric/number theory methods as appropriate. Put your final answer on the last line in the form '#### <answer>'.\n\n{question}"
        ]
        
        answers = []
        for prompt in prompts:
            # Call the frozen solver with each prompt variation
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            # Extract the answer from the last line starting with '#### '
            lines = response.strip().split('\n')
            for line in reversed(lines):
                if line.strip().startswith('#### '):
                    answer = line.strip()[5:].strip()
                    answers.append(answer)
                    break
            else:
                # Fallback: take the entire response if no marker found
                answers.append(response.strip())
        
        # Use majority voting to select the most common answer
        if answers:
            vote_counts = Counter(answers)
            most_common = vote_counts.most_common(1)[0][0]
            return most_common
        
        # Should never reach here, but return empty string as fallback
        return ""