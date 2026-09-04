"""This harness uses a repair mechanism: it executes generated SQL and feeds errors back for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        current_sql = None
        last_error = None
        
        for attempt in range(max_attempts):
            if attempt == 0:
                # First attempt: generate SQL from question
                prompt = f"Given the database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a valid SQL query to answer the question."
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            else:
                # Repair attempt: feed back error and previous SQL
                prompt = f"Given the database schema:\n{self.schema}\n\nQuestion: {question}\n\nPrevious SQL attempt:\n{current_sql}\n\nExecution error:\n{last_error}\n\nGenerate a corrected SQL query that fixes the error."
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            
            # Execute the current SQL
            result = self.execute(current_sql)
            if result.get("ok", False):
                return current_sql
            else:
                last_error = result.get("error", "Unknown error")
        
        # If all attempts failed, return the last generated SQL
        return current_sql