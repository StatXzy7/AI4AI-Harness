"""Implements a repair mechanism that iteratively refines SQL by executing and feeding back errors."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS1G4(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        error_msg = ""
        
        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = f"""Given the following database schema:\n{self.schema}\n\nAnswer the question: {question}\n\nGenerate a valid SQL query:"""
            else:
                prompt = f"""Given the following database schema:\n{self.schema}\n\nAnswer the question: {question}\n\nYour previous SQL query had an error: {error_msg}\n\nGenerate a corrected valid SQL query:"""
            
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql_text = bridge.extract_sql(response)
            
            result = self.execute(sql_text)
            if result["ok"]:
                return sql_text
            else:
                error_msg = result["error"]
        
        # If all attempts failed, return the last generated SQL (or empty string)
        return sql_text if attempt > 0 else ""