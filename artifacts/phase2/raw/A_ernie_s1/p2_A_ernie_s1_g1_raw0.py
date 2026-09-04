"""This harness uses error-driven SQL repair: it executes generated SQL and feeds execution errors back to the LLM for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS1G1(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        attempt = 0
        current_sql = None
        
        while attempt < max_attempts:
            attempt += 1
            
            # Initial or repair prompt
            if attempt == 1:
                prompt = f"Given the database schema:\n{self.schema}\n\nGenerate a SQL query to answer: {question}"
            else:
                prompt = f"Given the database schema:\n{self.schema}\n\nThe previous SQL query failed with error: {last_error}\n\nGenerate a corrected SQL query to answer: {question}"
            
            # Generate SQL
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            current_sql = bridge.extract_sql(response)
            
            # Execute the generated SQL
            result = self.execute(current_sql)
            
            # Check if execution was successful
            if result.get("ok", False):
                return current_sql
            
            # Store error for next iteration
            last_error = result.get("error", "Unknown error")
        
        # Return best attempt after max retries (even if failed)
        return current_sql