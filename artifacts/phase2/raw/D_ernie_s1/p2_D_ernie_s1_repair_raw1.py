"""A harness that generates SQL via LLM, executes it, and retries up to two times on error by feeding back the SQLite error."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS1Repair(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        # Initial prompt for the first attempt
        prompt = f"Given the following database schema:\n{schema}\n\nQuestion: {question}\n\nWrite a SQL query to answer the question. Return only the SQL query."
        sql = None
        for attempt in range(3):  # initial attempt + up to 2 retries
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            # Execute the generated SQL
            result = self.execute(sql)
            if result.get("ok", False):
                return sql
            # If execution failed, prepare error feedback for the next attempt
            error = result.get("error", "Unknown error")
            prompt = f"Given the following database schema:\n{schema}\n\nQuestion: {question}\n\nThe previous SQL query failed with error: {error}\n\nPlease fix the query. Return only the corrected SQL query."
        # If all attempts failed, return the last generated SQL
        return sql