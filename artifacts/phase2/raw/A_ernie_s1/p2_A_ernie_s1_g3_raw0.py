"""Uses iterative self-repair: executes generated SQL and feeds back execution errors to regenerate corrected queries."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS1G3(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: direct generation
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\nSQL:"
        raw = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        # Try up to 3 repair rounds on failure
        for attempt in range(3):
            result = self.execute(sql)
            if result.get("ok", False):
                return sql

            # Build repair prompt with the error
            error_info = result.get("error", "Unknown error")
            repair_prompt = (
                f"The following SQL query failed with error:\n"
                f"SQL: {sql}\n"
                f"Error: {error_info}\n\n"
                f"Given the following database schema:\n\n{self.schema}\n\n"
                f"Question: {question}\n"
                f"Please produce a corrected SQL query that fixes the error:\n"
            )
            raw = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(raw)

        # Return best attempt even if still broken
        return sql