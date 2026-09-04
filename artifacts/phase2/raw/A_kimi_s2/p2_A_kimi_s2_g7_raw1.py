"""A repair-loop harness: it generates SQL, executes it, and feeds execution errors back into the prompt for regeneration until the query runs or the attempt budget is exhausted."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G7(SQLHarness):
    """Text-to-SQL harness with an execution-feedback repair loop."""

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite developer. Given a database schema and a "
            "natural-language question, produce a single valid SQLite query that "
            "answers the question. Output only the SQL query, with no explanation "
            "or commentary."
        )

        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL query that answers the question."
        )

        prompt = base_prompt
        last_sql = ""
        last_error = None

        for _ in range(self.MAX_ATTEMPTS):
            response = self.llm(prompt, system=system, temperature=0.0, n=1)

            sql = bridge.extract_sql(response)
            if not sql:
                sql = response.strip()
            if not sql:
                prompt = (
                    base_prompt
                    + "\n\nYour previous reply contained no SQL. "
                    "Reply with ONLY the SQL query."
                )
                continue

            last_sql = sql
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            error = result.get("error") or "unknown execution error"
            if error == last_error:
                # Identical failure twice in a row: the model is stuck in a
                # loop, so further retries are unlikely to help.
                break
            last_error = error

            prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Your previous SQL query failed to execute.\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Execution error:\n{error}\n\n"
                "Fix the query. Verify that every table and column name matches "
                "the schema exactly, that the syntax is valid SQLite, and that "
                "the query still answers the original question. "
                "Reply with ONLY the corrected SQL query."
            )

        # All attempts exhausted: return the most recent candidate as best effort.
        return last_sql