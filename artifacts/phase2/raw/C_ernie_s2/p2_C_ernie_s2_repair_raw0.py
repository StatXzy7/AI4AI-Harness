"""Generate SQL with LLM, execute it, and retry up to two times feeding the exact SQLite error back on failure."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Generate a SQLite query for the given question using the frozen LLM,
        execute it via self.execute, and on failure feed the exact error back
        to the LLM for up to two additional attempts.
        """
        # Initial prompt for first attempt
        prompt = (
            f"Given the following database schema:\n\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Generate a SQLite SQL query that answers the question."
        )

        for attempt in range(3):  # initial + up to 2 retries
            raw_output = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(raw_output)

            # Execute the generated SQL
            result = self.execute(sql)

            # If execution succeeded, return the successful SQL
            if result.get("ok"):
                return sql

            # If this is the last attempt, return the last generated SQL anyway
            if attempt == 2:
                return sql

            # Prepare retry prompt with the exact error message
            error = result.get("error", "No error message provided")
            prompt = (
                f"The following SQL query failed with error: {error}\n\n"
                f"Original question: {question}\n\n"
                f"Schema: {self.schema}\n\n"
                f"Please correct the SQL query."
            )

        # Fallback (should never be reached)
        return ""