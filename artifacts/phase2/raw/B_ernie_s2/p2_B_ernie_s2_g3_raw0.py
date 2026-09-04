"""Uses iterative repair: executes generated SQL and feeds errors back to LLM for regeneration up to 3 attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        max_retries = 3
        prompt = f"Given the schema: {self.schema}\nQuestion: {question}\nSQL:"
        
        for attempt in range(max_retries):
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            
            if not sql:
                if attempt == max_retries - 1:
                    return ""
                continue
            
            result = self.execute(sql)
            if result["ok"]:
                return sql
            
            error_msg = result.get("error", "Unknown error")
            prompt = f"Given the schema: {self.schema}\nQuestion: {question}\nPrevious SQL: {sql}\nError: {error_msg}\nCorrected SQL:"
        
        return sql