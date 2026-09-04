"""Implements a repair mechanism that iteratively regenerates SQL after execution errors."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS2G1(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        attempt = 0
        current_sql = None
        last_error = None
        
        while attempt < max_attempts:
            if attempt == 0:
                prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a valid SQL query to answer the question."
            else:
                prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nPrevious SQL attempt:\n{current_sql}\n\nExecution error:\n{last_error}\n\nGenerate a corrected valid SQL query."
            
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            current_sql = bridge.extract_sql(response)
            
            result = self.execute(current_sql)
            if result["ok"]:
                return current_sql
            else:
                last_error = result["error"]
                attempt += 1
        
        return current_sql