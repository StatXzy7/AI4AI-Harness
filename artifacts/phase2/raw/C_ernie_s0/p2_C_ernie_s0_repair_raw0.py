"""Harness that generates SQL via LLM, executes it, and retries up to two times on error using the SQLite error message."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS0Repair(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial prompt for the first attempt
        prompt = (
            f"Given the following database schema:\n\n{self.schema}\n\n"
            f"Answer the following question with a SQL query: {question}"
        )

        for attempt in range(3):  # initial + 2 retries
            # Generate SQL using the frozen LLM (temperature=0, n=1)
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            # Extract SQL from the LLM's response
            sql = bridge.extract_sql(response)
            # Execute the SQL against the database
            result = self.execute(sql)

            if result["ok"]:
                return sql

            # If execution failed, prepare a new prompt that includes the error
            error_msg = result["error"]
            prompt = (
                f"The following SQL query failed with error: {error_msg}\n\n"
                f"SQL: {sql}\n\n"
                f"Given the database schema:\n\n{self.schema}\n\n"
                f"Answer the following question with a corrected SQL query: {question}"
            )

        # If all attempts failed, return the last generated SQL
        return sql