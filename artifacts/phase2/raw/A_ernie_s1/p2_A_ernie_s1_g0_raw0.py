"""Repair mechanism: generate SQL, execute it, and regenerate on execution errors up to a retry limit."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS1G0(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL from the question
        prompt = f"Given the schema:\n{self.schema}\n\nWrite a SQL query to answer: {question}"
        sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_text)

        # Try executing up to 3 times, repairing on error
        for attempt in range(3):
            result = self.execute(sql)
            if result.get("ok", False):
                return sql

            # If execution failed, feed the error back for regeneration
            error_msg = result.get("error", "Unknown error")
            repair_prompt = (
                f"Given the schema:\n{self.schema}\n\n"
                f"Original question: {question}\n\n"
                f"Your previous SQL query was:\n{sql}\n\n"
                f"Execution failed with error: {error_msg}\n\n"
                f"Write a corrected SQL query that fixes the error."
            )
            sql_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_text)

        # Return best effort even after retries exhausted
        return sql