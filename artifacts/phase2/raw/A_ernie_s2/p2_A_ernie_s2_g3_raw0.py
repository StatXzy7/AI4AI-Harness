"""Uses error-driven repair: executes generated SQL, feeds execution errors back for regeneration up to 3 attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        max_retries = 3
        current_sql = None
        error_msg = None
        
        for attempt in range(max_retries + 1):
            if attempt == 0:
                # First attempt: generate SQL from question alone
                prompt = f"Generate SQL for: {question}\nSQL:"
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            else:
                # Repair attempt: include previous SQL and error
                prompt = (
                    f"The following SQL failed with error:\n"
                    f"SQL: {current_sql}\n"
                    f"Error: {error_msg}\n"
                    f"Fix the SQL for: {question}\n"
                    f"SQL:"
                )
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            
            # Execute the current SQL
            result = self.execute(current_sql)
            if result["ok"]:
                return current_sql
            
            # Prepare for next attempt if not last
            if attempt < max_retries:
                error_msg = result.get("error", "Unknown error")
        
        # If all retries failed, return the last attempted SQL
        return current_sql