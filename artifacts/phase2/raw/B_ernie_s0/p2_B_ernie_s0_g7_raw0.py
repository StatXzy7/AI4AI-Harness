"""This harness uses error-driven repair: it executes generated SQL and iteratively refines it using execution feedback."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BErnieS0G7(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Generate SQL for the given question, execute it, and repair on errors.
        Returns the final, executable SQL string.
        """
        # Initial prompt for SQL generation
        prompt = f"Question: {question}\nSchema: {self.schema}\nWrite a single SQL query that answers the question."
        sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_text)

        max_attempts = 3
        for attempt in range(max_attempts):
            result = self.execute(sql)
            if result.get("ok", False):
                return sql

            # Build repair prompt using the error information
            error_msg = result.get("error", "Unknown error")
            repair_prompt = (
                f"Question: {question}\n"
                f"Schema: {self.schema}\n"
                f"Previous SQL: {sql}\n"
                f"Execution error: {error_msg}\n"
                f"Fix the SQL so it runs correctly."
            )
            sql_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_text)

        # If all attempts fail, return the last generated SQL (may still be incorrect)
        return sql