"""Uses self-consistency with multiple diverse prompts to select the most common answer from several independent greedy generations."""

import random
from collections import Counter
from ..harness_base import MathHarness


class GsmGsmErnieS0G4(MathHarness):
    def solve(self, question: str) -> str:
        """Solve a competition-math word problem using self-consistency over multiple prompt variations."""
        # Generate multiple diverse prompts to encourage different reasoning paths
        prompt_variations = [
            f"Solve the following problem step by step. {question}",
            f"Let's think carefully about this problem. {question}",
            f"Work through this problem systematically. {question}",
            f"Break down this problem into smaller parts. {question}",
            f"Consider different approaches to solve this. {question}",
        ]
        
        # Add random seeds to further diversify the prompts
        diverse_prompts = []
        for base_prompt in prompt_variations:
            seed = random.randint(0, 10000)
            diverse_prompts.append(f"{base_prompt} (Seed: {seed})")
        
        # Generate multiple independent solutions
        answers = []
        for prompt in diverse_prompts:
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            # Extract the final answer from the last line starting with '#### '
            lines = response.strip().split('\n')
            for line in reversed(lines):
                if line.strip().startswith('#### '):
                    answer = line.strip()[5:].strip()
                    answers.append(answer)
                    break
            else:
                # Fallback: use entire response if no marker found
                answers.append(response.strip())
        
        # Use majority voting to select the most consistent answer
        answer_counts = Counter(answers)
        most_common_answer = answer_counts.most_common(1)[0][0]
        
        return most_common_answer