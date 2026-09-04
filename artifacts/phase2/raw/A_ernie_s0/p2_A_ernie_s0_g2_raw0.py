"""Repair mechanism: execute generated SQL and iteratively regenerate on errors until success or max retries."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS0G2(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL from question + schema
        prompt = f"Given the database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nGenerate a valid SQL query that answers the question."
        raw = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        # Try to execute; on error, repair up to MAX_RETRIES times
        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES + 1):
            result = self.execute(sql)
            if result.get("ok", False):
                return sql

            # If we've exhausted retries, return the last attempt anyway
            if attempt == MAX_RETRIES:
                return sql

            # Construct repair prompt with the error message
            repair_prompt = (
                f"The following SQL query failed with error:\n"
                f"SQL: {sql}\n"
                f"Error: {result.get('error', 'Unknown error')}\n\n"
                f"Given the database schema:\n\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Generate a corrected SQL query that avoids the error and answers the question."
            )
            raw = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(raw)

        return sql