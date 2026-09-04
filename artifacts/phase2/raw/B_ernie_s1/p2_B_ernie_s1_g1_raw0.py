"""Repair mechanism: execute initial SQL and feed execution errors back for one regeneration attempt."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS1G1(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL from question and schema
        prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a valid SQL query to answer the question."
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        
        # Execute the first SQL
        result = self.execute(sql)
        
        # If successful, return the SQL
        if result.get("ok", False):
            return sql
        
        # If there was an error, prepare a repair prompt
        error_msg = result.get("error", "Unknown error")
        repair_prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nThe following SQL query failed with error:\n{error_msg}\n\nOriginal SQL: {sql}\n\nGenerate a corrected valid SQL query."
        repair_response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
        repaired_sql = bridge.extract_sql(repair_response)
        
        # Execute the repaired SQL (but don't attempt further repairs)
        repaired_result = self.execute(repaired_sql)
        if repaired_result.get("ok", False):
            return repaired_sql
        
        # If still fails, return the last generated SQL (or original if extraction fails)
        return repaired_sql if repaired_sql else sql