"""Harness that extracts and enforces hint constraints from the question as hard requirements in the LLM prompt for Text-to-SQL."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS0HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Parse the 'Hint:' line from the question
        hint_constraint = ""
        for line in question.split('\n'):
            if line.strip().startswith('Hint:'):
                hint_constraint = line.strip()[len('Hint:'):].strip()
                break
        
        # Construct the prompt with hard requirement if hint exists
        if hint_constraint:
            prompt = (
                f"{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"IMPORTANT HARD REQUIREMENT: {hint_constraint}\n\n"
                f"Write SQL to answer the question, strictly following the above requirement."
            )
        else:
            prompt = (
                f"{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Write SQL to answer the question."
            )
        
        # Call the frozen weak solver (LLM)
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        
        # Extract SQL from the response
        final_sql = bridge.extract_sql(response)
        
        return final_sql