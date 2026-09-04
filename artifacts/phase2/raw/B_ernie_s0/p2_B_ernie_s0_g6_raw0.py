"""Repair mechanism: execute generated SQL and feed execution errors back to LLM for up to two regeneration attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BErnieS0G6(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL directly from question + schema
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nWrite a SQL query to answer: {question}"
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)

        # Try up to 2 repair attempts if execution fails
        for attempt in range(3):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            # Build repair prompt with the error feedback
            error_msg = result.get("error", "Unknown error")
            repair_prompt = (
                f"The following SQL query failed to execute:\n\n{sql}\n\n"
                f"Error: {error_msg}\n\n"
                f"Given the database schema:\n\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Write a corrected SQL query that fixes the error."
            )
            repair_response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(repair_response)

        # If all attempts failed, return the last generated SQL
        return sql