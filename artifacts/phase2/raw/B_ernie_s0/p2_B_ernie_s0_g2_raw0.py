"""This harness uses an error-repair loop where SQL execution failures are fed back to the LLM for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS0G2(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        current_sql = None
        error_msg = None
        
        for attempt in range(max_attempts):
            if attempt == 0:
                # First attempt: generate SQL from question and schema
                prompt = f"Schema: {self.schema}\nQuestion: {question}\nSQL:"
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            else:
                # Subsequent attempts: include error feedback
                prompt = f"Schema: {self.schema}\nQuestion: {question}\nPrevious SQL: {current_sql}\nError: {error_msg}\nPlease fix the SQL:"
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            
            # Execute the generated SQL
            result = self.execute(current_sql)
            if result["ok"]:
                return current_sql
            else:
                error_msg = result.get("error", "Unknown error")
        
        # If all attempts failed, return the last generated SQL
        return current_sql