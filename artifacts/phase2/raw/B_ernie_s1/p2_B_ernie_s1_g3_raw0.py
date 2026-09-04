"""A harness that iteratively repairs SQL queries by executing them and feeding errors back for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS1G3(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        current_sql = None
        current_error = None
        
        for attempt in range(max_attempts):
            if attempt == 0:
                # Initial generation
                prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nWrite a SQL query to answer the question."
            else:
                # Repair generation with error feedback
                prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nPrevious SQL attempt failed with error: {current_error}\n\nPrevious SQL: {current_sql}\n\nWrite a corrected SQL query."
            
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            current_sql = bridge.extract_sql(response)
            
            # Execute the current SQL
            result = self.execute(current_sql)
            
            if result["ok"]:
                return current_sql
            
            current_error = result["error"]
        
        # Return the last generated SQL even if all attempts failed
        return current_sql