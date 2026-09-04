"""Harness that uses repair: executes generated SQL and regenerates on error feedback."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2BErnieS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial prompt for first attempt
        prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a SQL query that answers the question."
        sql = None
        # Allow up to 3 attempts to repair failing queries
        for attempt in range(3):
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            result = self.execute(sql)
            if result["ok"]:
                return sql
            else:
                # Feed the error back into the prompt for the next attempt
                prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nPrevious SQL query: {sql}\nExecution error: {result['error']}\n\nPlease correct the SQL query."
        # Return the last generated SQL even if all attempts failed
        return sql