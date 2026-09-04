"""Generates SQL and repairs it using execution errors until a valid query is obtained."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS1G7(SQLHarness):
    def solve(self, question: str) -> str:
        sql = None
        error = None

        for _ in range(3):
            prompt = self._build_prompt(question, sql, error)
            sql = self._generate_sql(prompt)

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "Unknown error")

        return sql

    def _build_prompt(self, question: str, bad_sql: str | None, error: str | None) -> str:
        if bad_sql is None:
            return (
                "Given the following SQLite database schema:\n"
                f"{self.schema}\n\n"
                "Write a single SQL query that answers the user question. "
                "Output only the SQL query, with no explanation.\n\n"
                f"Question: {question}"
            )

        return (
            "Given the following SQLite database schema:\n"
            f"{self.schema}\n\n"
            "A previous SQL query failed. Please correct it.\n"
            f"Question: {question}\n"
            f"Previous SQL: {bad_sql}\n"
            f"Execution error: {error}\n\n"
            "Write a corrected SQL query. Output only the SQL query, with no explanation."
        )

    def _generate_sql(self, prompt: str) -> str:
        raw = self.llm(
            prompt,
            system="You are an expert SQLite SQL generator.",
            temperature=0.0,
            n=1,
        )

        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        if not isinstance(raw, str):
            raw = str(raw)

        return bridge.extract_sql(raw)