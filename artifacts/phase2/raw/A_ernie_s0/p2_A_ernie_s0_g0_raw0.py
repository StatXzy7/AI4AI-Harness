"""Repair mechanism that executes generated SQL and feeds back execution errors for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL from question + schema
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nWrite a valid SQL query that answers the question. Output only the SQL query."
        sql = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql)

        # Try up to 3 repair attempts
        for attempt in range(3):
            result = self.execute(sql)
            if result.get("ok", False):
                return sql

            # Repair: feed the error back into a regeneration prompt
            repair_prompt = (
                f"Given the following database schema:\n\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Your previous SQL query was:\n{sql}\n\n"
                f"The database returned this error:\n{result.get('error', 'Unknown error')}\n\n"
                f"Write a corrected valid SQL query that answers the question. Output only the SQL query."
            )
            sql = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql)

        # If all repair attempts fail, return the last generated SQL
        return sql