"""Iteratively generates SQL and repairs it with execution feedback until a useful result is obtained."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        previous_sql = None
        feedback = ""
        last_sql = ""

        system_prompt = (
            "You are a SQL expert. You write and fix SQLite queries based on a provided schema and question."
        )

        for _ in range(max_attempts):
            if previous_sql is None:
                prompt = self._initial_prompt(question)
            else:
                prompt = self._repair_prompt(question, previous_sql, feedback)

            raw = self.llm(prompt, system=system_prompt, temperature=0.0, n=1)
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""
            sql = bridge.extract_sql(raw)

            if not sql:
                feedback = (
                    "The previous response did not contain a valid SQL query. "
                    "Please output only a SQLite SELECT query."
                )
                # Force the next attempt to use the repair prompt.
                if previous_sql is None:
                    previous_sql = ""
                continue

            last_sql = sql
            result = self.execute(sql)

            if result.get("ok"):
                rows = result.get("rows", [])
                if rows:
                    return sql

                if previous_sql is not None and sql.strip().lower() == previous_sql.strip().lower():
                    return sql

                feedback = (
                    "The SQL executed successfully but returned zero rows. If that is likely incorrect "
                    "for the question, write a corrected SQL query. If zero rows is acceptable, output "
                    "exactly the same SQL query."
                )
                previous_sql = sql
            else:
                error = result.get("error", "Unknown error")
                if previous_sql is not None and sql.strip().lower() == previous_sql.strip().lower():
                    return sql

                feedback = (
                    f"The SQL execution failed with error: {error}. "
                    "Please fix the SQL query and output only the corrected SQL."
                )
                previous_sql = sql

        return last_sql

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SELECT query that answers this question.\n"
            "Output only the SQL query, no explanation."
        )

    def _repair_prompt(self, question: str, previous_sql: str, feedback: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Previous SQL:\n{previous_sql}\n\n"
            f"Feedback:\n{feedback}\n\n"
            "Write a corrected SQLite SELECT query.\n"
            "Output only the SQL query, no explanation."
        )