"""This harness uses a repair mechanism that iteratively refines SQL queries based on execution errors."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS0G6(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        current_prompt = f"Question: {question}\nSchema: {self.schema}\nGenerate SQL query:"
        
        for attempt in range(max_attempts):
            sql_text = self.llm(current_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_text)
            result = self.execute(sql)
            
            if result["ok"]:
                return sql
            else:
                error_msg = result.get("error", "Unknown error")
                current_prompt = f"Question: {question}\nSchema: {self.schema}\nThe previous SQL query failed with error: {error_msg}\nPlease generate a corrected SQL query:"
        
        return sql