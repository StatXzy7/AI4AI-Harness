"""Repair mechanism that iteratively refines SQL by executing and feeding back errors to the LLM."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a SQL query to answer the question. Only output the SQL query."
        
        for attempt in range(max_attempts):
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            result = self.execute(sql)
            
            if result["ok"]:
                return sql
            
            if attempt < max_attempts - 1:
                error_msg = result.get("error", "Unknown error")
                prompt = f"{prompt}\n\nThe previous SQL query failed with error: {error_msg}\nPlease generate a corrected SQL query."
        
        return sql