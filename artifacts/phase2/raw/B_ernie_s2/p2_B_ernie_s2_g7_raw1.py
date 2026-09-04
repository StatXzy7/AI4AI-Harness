"""Uses execution error feedback to iteratively repair generated SQL queries until they succeed or max attempts are reached."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        current_sql = None
        error_context = ""
        
        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\nSQL:"
            else:
                prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nThe previous SQL query failed with error: {error_context}\nPlease generate a corrected SQL query:\nSQL:"
            
            generated_text = self.llm(prompt, system="", temperature=0.0, n=1)
            current_sql = bridge.extract_sql(generated_text)
            
            result = self.execute(current_sql)
            if result["ok"]:
                return current_sql
            else:
                error_context = result["error"]
        
        return current_sql