"""Parses the Hint: line from the question and enforces its constraints via iterative SQL generation with validation."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Extract the Hint: line from the question
        hint = None
        for line in question.split('\n'):
            if line.strip().startswith('Hint:'):
                hint = line.strip()[len('Hint:'):].strip()
                break
        
        # Step 2: If no hint, fall back to standard generation
        if hint is None:
            prompt = f"Given the schema: {self.schema}\nQuestion: {question}\nWrite SQL."
            sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
            return bridge.extract_sql(sql_text)
        
        # Step 3: Iterative generation with hint enforcement
        for attempt in range(3):  # Allow up to 3 attempts
            # Construct prompt that restates hint as hard requirement
            prompt = (
                f"Given the schema: {self.schema}\n"
                f"Question: {question}\n"
                f"Hard requirement from hint: {hint}\n"
                f"Write SQL that strictly satisfies this requirement."
            )
            sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
            candidate_sql = bridge.extract_sql(sql_text)
            
            # Step 4: Validate candidate against hint using LLM as judge
            validation_prompt = (
                f"Hint requirement: {hint}\n"
                f"Candidate SQL: {candidate_sql}\n"
                f"Does this SQL strictly satisfy the hint? Answer 'Yes' or 'No'."
            )
            validation = self.llm(validation_prompt, system="", temperature=0.0, n=1)
            
            if 'Yes' in validation:
                return candidate_sql
        
        # Step 5: Return best candidate after attempts
        return candidate_sql