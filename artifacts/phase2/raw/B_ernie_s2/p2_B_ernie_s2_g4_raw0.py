"""
This harness uses a repair mechanism: it executes the generated SQL and if there's an error, it regenerates with the error feedback.
"""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL from schema and question
        prompt = f"Given the schema: {self.schema}\nQuestion: {question}\nGenerate SQL to answer the question."
        sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_text)
        
        # Execute the generated SQL
        result = self.execute(sql)
        
        # If execution succeeds, return the SQL
        if result["ok"]:
            return sql
        
        # If execution fails, attempt repair with error feedback
        repair_prompt = f"Given the schema: {self.schema}\nQuestion: {question}\nThe previous SQL attempt was: {sql}\nIt produced the error: {result['error']}\nPlease fix the SQL."
        repair_sql_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
        repair_sql = bridge.extract_sql(repair_sql_text)
        
        # Execute the repaired SQL
        repair_result = self.execute(repair_sql)
        
        # Return the repaired SQL regardless of success (as per mechanism)
        return repair_sql