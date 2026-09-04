"""This harness uses a repair mechanism: it executes the generated SQL and feeds execution errors back for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS1G6(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial generation attempt
        prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a SQL query to answer the question."
        initial_text = self.llm(prompt, system="", temperature=0.0, n=1)
        initial_sql = bridge.extract_sql(initial_text)
        
        # Execute the initial SQL
        result = self.execute(initial_sql)
        
        # If successful, return the SQL
        if result["ok"]:
            return initial_sql
        
        # Repair attempt: feed error back to LLM
        error_prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nThe following SQL query was generated but caused an error:\n{initial_sql}\n\nError message: {result['error']}\n\nGenerate a corrected SQL query that avoids this error."
        repair_text = self.llm(error_prompt, system="", temperature=0.0, n=1)
        repair_sql = bridge.extract_sql(repair_text)
        
        # Execute the repaired SQL
        repair_result = self.execute(repair_sql)
        if repair_result["ok"]:
            return repair_sql
        
        # If repair still fails, return the initial SQL (or could return repair_sql as fallback)
        return repair_sql