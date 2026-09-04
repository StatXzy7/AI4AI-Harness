"""Implements a repair mechanism that executes generated SQL and iteratively refines it using execution errors."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        current_sql = None
        
        for attempt in range(max_attempts):
            if attempt == 0:
                # First attempt: generate initial SQL
                prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nWrite a SQL query to answer the question."
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            else:
                # Subsequent attempts: include error feedback
                prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nThe following SQL query failed with error: {last_error}\n\nThe previous SQL was: {current_sql}\n\nPlease write a corrected SQL query."
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            
            # Execute the current SQL
            result = self.execute(current_sql)
            
            if result["ok"]:
                return current_sql
            
            last_error = result["error"]
        
        # If all attempts failed, return the last generated SQL
        return current_sql