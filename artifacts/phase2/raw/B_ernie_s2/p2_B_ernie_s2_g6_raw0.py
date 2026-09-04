"""A repair mechanism that executes generated SQL and feeds back errors for iterative refinement."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nAnswer the following question with a SQL query:\n{question}"
        
        for attempt in range(max_attempts):
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            
            result = self.execute(sql)
            if result["ok"]:
                return sql
            
            # Prepare repair prompt with error feedback
            error_msg = result.get("error", "Unknown error")
            repair_prompt = f"The following SQL query failed with error: {error_msg}\n\n"
            repair_prompt += f"Schema:\n{self.schema}\n\n"
            repair_prompt += f"Question: {question}\n\n"
            repair_prompt += f"Previous SQL: {sql}\n\n"
            repair_prompt += "Please generate a corrected SQL query that resolves the error."
            
            prompt = repair_prompt
        
        # Return the last attempt even if it failed (or could return empty/placeholder)
        return sql