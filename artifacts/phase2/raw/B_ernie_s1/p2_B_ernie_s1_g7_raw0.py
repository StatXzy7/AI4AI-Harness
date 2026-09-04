"""This harness uses a repair mechanism that executes generated SQL and feeds errors back for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS1G7(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        prompt = f"Question: {question}\nSchema: {self.schema}\nGenerate SQL:"
        
        for attempt in range(max_attempts):
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            result = self.execute(sql)
            
            if result["ok"]:
                return sql
            
            if attempt < max_attempts - 1:
                prompt = f"Question: {question}\nSchema: {self.schema}\nPrevious SQL: {sql}\nError: {result['error']}\nPlease correct the SQL:"
        
        return sql