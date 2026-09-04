"""Harness that generates SQL via an LLM, executes it, and self-repairs on SQLite errors up to two retries."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        last_sql = ""
        last_error = ""
        max_attempts = 3  # initial + 2 repairs

        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = (
                    "You are a SQL expert. Given the following database schema and a natural "
                    "language question, write a valid SQLite query that answers the question.\n\n"
                    f"Schema:\n{schema}\n\n"
                    f"Question: {question}\n\n"
                    "Return only the SQL query, with no explanation, no markdown, and no code fences."
                )
            else:
                prompt = (
                    "You are a SQL expert. The following SQLite query failed with an error. "
                    "Fix the query so that it runs correctly against the schema below.\n\n"
                    f"Schema:\n{schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Failed SQL:\n{last_sql}\n\n"
                    f"SQLite Error:\n{last_error}\n\n"
                    "Return only the corrected SQL query, with no explanation, no markdown, "
                    "and no code fences."
                )

            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            if not sql:
                # If extraction failed, try again with a coerced extraction.
                sql = (response or "").strip()
                # Strip common markdown fences if present.
                if sql.startswith("