"""This harness generates SQL, executes it, and repairs errors by re-generating with error feedback."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G5(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        sql_text = None
        error = None
        
        for attempt in range(max_attempts):
            if attempt == 0:
                # Initial generation without any error feedback
                prompt = f"Question: {question}\nSchema: {self.schema}\nGenerate SQL."
            else:
                # Subsequent generation with error feedback
                prompt = f"Question: {question}\nSchema: {self.schema}\nPrevious SQL: {sql_text}\nError: {error}\nGenerate a corrected SQL."
            
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql_text = bridge.extract_sql(response)
            
            result = self.execute(sql_text)
            if result["ok"]:
                return sql_text
            error = result["error"]
        
        # Return the last generated SQL if all attempts failed
        return sql_text