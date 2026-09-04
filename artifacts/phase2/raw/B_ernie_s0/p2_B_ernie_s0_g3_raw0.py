"""Uses SQL execution errors to iteratively repair generated queries until success or max attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        attempt = 0
        last_error = None
        
        while attempt < max_attempts:
            if attempt == 0:
                prompt = f"Given the schema: {self.schema}\n\nQuestion: {question}\n\nGenerate a valid SQL query:"
            else:
                prompt = f"Given the schema: {self.schema}\n\nQuestion: {question}\n\nYour previous SQL query failed with error: {last_error}\n\nGenerate a corrected SQL query:"
            
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            
            result = self.execute(sql)
            if result["ok"]:
                return sql
            
            last_error = result.get("error", "Unknown error")
            attempt += 1
        
        # Return the last generated SQL even if it failed (as fallback)
        return sql