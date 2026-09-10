"""A harness that implements a multi-step verification and refinement process for competition math problems."""

from ..harness_base import MathHarness
from typing import Optional, Tuple
import re


class GsmGsmKimiS0G4(MathHarness):
    def solve(self, question: str) -> str:
        """
        Solve using a multi-step process:
        1. Generate initial solution with step-by-step reasoning
        2. Verify solution by checking each step for logical consistency
        3. Generate alternative solutions using different problem-solving strategies
        4. Use majority voting on final answers from different approaches
        5. If voting fails, attempt to identify and correct potential errors
        """
        
        # Step 1: Generate initial solution with detailed reasoning
        initial_prompt = f"""Solve this math problem step by step. Show all your work and reasoning.

Question: {question}

Please write your solution in this exact format:
Step 1: [First step of reasoning]
Step 2: [Second step of reasoning]
...
Final Answer: #### [your answer]"""

        initial_solution = self.llm(initial_prompt, system="You are an expert mathematician solving competition math problems. Be precise and thorough.", temperature=0.0, n=1)
        
        # Step 2: Generate verification and potential error analysis
        verification_prompt = f"""Analyze this math solution for errors or inconsistencies.

Question: {question}

Initial Solution:
{initial_solution}

Please:
1. Check each step for mathematical correctness
2. Identify any potential errors or jumps in reasoning
3. If you find errors, provide a corrected solution
4. If the solution appears correct, confirm it

Output your analysis and corrected solution (if any) in this format:
Analysis: [Your analysis]
Corrected Solution: [If errors found, provide corrected solution; otherwise write "No corrections needed"]
Final Answer: #### [your final answer]"""

        verification = self.llm(verification_prompt, system="You are a careful math proof checker. Verify each step rigorously.", temperature=0.0, n=1)
        
        # Step 3: Generate alternative approach using a different strategy
        alternative_prompt = f"""Solve this math problem using a completely different approach than standard algebraic manipulation.

Question: {question}

Try one of these alternative strategies:
- Work backwards from the answer
- Use geometric intuition
- Apply dimensional analysis
- Consider edge cases or special values
- Use estimation and refinement

Show your alternative solution and end with:
Final Answer: #### [your answer]"""

        alternative_solution = self.llm(alternative_prompt, system="You are a creative mathematician who approaches problems from unconventional angles.", temperature=0.0, n=1)
        
        # Step 4: Extract and compare answers
        answers = []
        
        # Extract answer from initial solution
        initial_answer = self._extract_answer(initial_solution)
        if initial_answer:
            answers.append(initial_answer)
        
        # Extract answer from verification/corrected solution
        verified_answer = self._extract_answer(verification)
        if verified_answer:
            answers.append(verified_answer)
        
        # Extract answer from alternative approach
        alt_answer = self._extract_answer(alternative_solution)
        if alt_answer:
            answers.append(alt_answer)
        
        # Step 5: Majority voting or error correction
        if len(answers) >= 2:
            # Check if at least two answers agree
            from collections import Counter
            answer_counts = Counter(answers)
            most_common = answer_counts.most_common(1)
            
            if most_common and most_common[0][1] >= 2:
                # At least two answers agree - use this
                return most_common[0][0]
            
            # If no majority, try to identify which answer might be correct
            final_answer = self._resolve_conflicting_answers(question, answers, initial_solution, verification, alternative_solution)
            if final_answer:
                return final_answer
        
        # Fallback: Use the verified answer if available, else initial
        if verified_answer:
            return verified_answer
        elif initial_answer:
            return initial_answer
        elif alt_answer:
            return alt_answer
        
        # Last resort: Ask for final answer extraction
        final_prompt = f"""From the following solutions, extract the most likely correct final answer.

Question: {question}

Solutions:
1. {initial_solution}
2. {verification}
3. {alternative_solution}

Consider which solution appears most mathematically sound. Output only:
#### [your final answer]"""

        final_response = self.llm(final_prompt, system="Extract the most reliable final answer from these solutions.", temperature=0.0, n=1)
        final_answer = self._extract_answer(final_response)
        return final_answer if final_answer else "ERROR"
    
    def _extract_answer(self, text: str) -> Optional[str]:
        """Extract the answer from text after the last '####' marker."""
        lines = text.strip().split('\n')
        for line in reversed(lines):
            if '####' in line:
                # Extract everything after ####
                answer_part = line.split('####', 1)[1].strip()
                # Clean up the answer
                answer = answer_part.strip()
                # Remove any trailing period
                if answer.endswith('.'):
                    answer = answer[:-1].strip()
                return answer
        return None
    
    def _resolve_conflicting_answers(self, question: str, answers: list, 
                                   solution1: str, solution2: str, solution3: str) -> Optional[str]:
        """Attempt to resolve conflicting answers by asking for expert judgment."""
        resolution_prompt = f"""We have conflicting answers to a math problem. Please help determine which is correct.

Question: {question}

Proposed answers: {', '.join(set(answers))}

Approach 1 Solution:
{solution1}

Approach 2 Solution:
{solution2}

Approach 3 Solution:
{solution3}

Please:
1. Examine which approach seems most mathematically rigorous
2. Check for common calculation errors in each approach
3. Determine which answer is most likely correct

Output your final determination as:
#### [your answer]"""

        resolution = self.llm(resolution_prompt, system="You are an expert mathematician arbitrating between different solutions.", temperature=0.0, n=1)
        return self._extract_answer(resolution)