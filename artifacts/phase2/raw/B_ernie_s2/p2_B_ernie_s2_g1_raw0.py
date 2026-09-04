"""Harness that iteratively repairs SQL queries using execution error feedback."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS2G1(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial generation
        prompt = f"Given the schema: {self.schema}\n\nQuestion: {question}\n\nGenerate a SQL query:"
        sql = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql)
        
        # Attempt to execute and repair up to 3 times
        for attempt in range(3):
            result = self.execute(sql)
            if result["ok"]:
                return sql
            # Feed error back for regeneration
            repair_prompt = f"Given the schema: {self.schema}\n\nQuestion: {question}\n\nPrevious SQL: {sql}\n\nError: {result['error']}\n\nGenerate a corrected SQL query:"
            sql = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql)
        
        # Return last attempt even if failed
        return sql