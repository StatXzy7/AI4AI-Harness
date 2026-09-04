"""Uses iterative repair: executes generated SQL, then feeds execution errors back to the LLM for correction up to 3 attempts."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        max_retries = 3
        current_sql = None
        
        for attempt in range(max_retries):
            if attempt == 0:
                # First attempt: generate SQL from question and schema
                prompt = f"Given the database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate the SQL query:"
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            else:
                # Subsequent attempts: generate corrected SQL with error feedback
                prompt = f"Given the database schema:\n{self.schema}\n\nQuestion: {question}\n\nPrevious SQL attempt failed with error:\n{last_error}\n\nGenerate a corrected SQL query:"
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            
            # Execute the generated SQL
            result = self.execute(current_sql)
            
            if result["ok"]:
                return current_sql
            
            last_error = result["error"]
        
        # If all retries failed, return the last generated SQL (or could return empty/error)
        return current_sql if current_sql else ""