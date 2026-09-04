"""Harness that uses error-driven repair: executes generated SQL and regenerates on failure."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS0G4(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        last_sql = None
        last_error = None
        
        # Initial prompt for the first attempt
        current_prompt = f"Question: {question}\nSchema: {self.schema}\nWrite a SQL query to answer the question."
        
        for attempt in range(max_attempts):
            # Generate SQL using the frozen LLM
            response = self.llm(current_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            last_sql = sql
            
            # Execute the generated SQL
            result = self.execute(sql)
            if result["ok"]:
                return sql
            else:
                last_error = result["error"]
                # Prepare a repair prompt that includes the error for the next attempt
                current_prompt = f"The following SQL query failed with error: {last_error}\nOriginal question: {question}\nSchema: {self.schema}\nPlease fix the SQL query."
        
        # Return the last generated SQL even if all attempts failed
        return last_sql