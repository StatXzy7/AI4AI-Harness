"""This harness repairs SQL queries by re-generating with execution error feedback."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        base_prompt = f"Given the schema: {schema}\n\nQuestion: {question}\n\nGenerate SQL:"
        prompt = base_prompt
        sql = None
        error = None
        max_attempts = 3
        
        for attempt in range(max_attempts):
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            if sql is None:
                sql = ""
            result = self.execute(sql)
            if result["ok"]:
                return sql
            error = result["error"]
            if attempt < max_attempts - 1:
                prompt = base_prompt + f"\nPrevious SQL: {sql}\nError: {error}\nGenerate a corrected SQL:"
        
        return sql