"""Implements a repair mechanism that executes generated SQL and uses execution errors to guide regeneration up to 3 times."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 4  # Initial attempt + 3 repair attempts
        current_sql = None
        current_error = None
        
        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = f"Given the schema: {self.schema}\nQuestion: {question}\nGenerate SQL:"
            else:
                prompt = f"Given the schema: {self.schema}\nQuestion: {question}\nThe previous SQL failed: {current_sql}\nError: {current_error}\nPlease generate a corrected SQL:"
            
            sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
            current_sql = bridge.extract_sql(sql_text)
            
            result = self.execute(current_sql)
            if result["ok"]:
                return current_sql
            current_error = result["error"]
        
        return current_sql