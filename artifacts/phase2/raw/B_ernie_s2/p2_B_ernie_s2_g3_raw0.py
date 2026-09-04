"""Implements a repair-based mechanism where SQL execution errors are fed back to the LLM for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        current_attempt = 0
        last_error = None
        
        while current_attempt < max_attempts:
            if current_attempt == 0:
                prompt = f"Given the following database schema:\n\n{self.schema}\n\nAnswer the question: {question}"
                system = "You are a SQL expert. Generate only the SQL query without any explanation."
            else:
                prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nPrevious SQL attempt:\n{last_sql}\n\nError from execution:\n{last_error}\n\nGenerate a corrected SQL query."
                system = "You are a SQL expert. Fix the error in the previous SQL query. Generate only the corrected SQL query without any explanation."
            
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            
            result = self.execute(sql)
            
            if result["ok"]:
                return sql
            else:
                last_sql = sql
                last_error = result["error"]
                current_attempt += 1
        
        return last_sql