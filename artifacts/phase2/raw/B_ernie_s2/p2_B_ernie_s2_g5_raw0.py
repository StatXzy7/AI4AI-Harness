"""Harness that iteratively repairs SQL queries by feeding execution errors back to the LLM for up to two correction attempts."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G5(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        current_sql = None
        error_msg = None
        
        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nGenerate the SQL query to answer the question."
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            else:
                prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nPrevious SQL attempt:\n{current_sql}\n\nExecution error: {error_msg}\n\nPlease generate a corrected SQL query."
                response = self.llm(prompt, system="", temperature=0.0, n=1)
                current_sql = bridge.extract_sql(response)
            
            result = self.execute(current_sql)
            if result["ok"]:
                return current_sql
            else:
                error_msg = result.get("error", "Unknown error")
        
        return current_sql