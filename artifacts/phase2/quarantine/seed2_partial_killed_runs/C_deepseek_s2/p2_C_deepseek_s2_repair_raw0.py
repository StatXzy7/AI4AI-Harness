"""Generates SQL, executes it, and uses exact SQLite error feedback to regenerate up to two times if execution fails."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        error = None
        previous_sql = None
        sql = self._generate_sql(question, error, previous_sql)

        for attempt in range(3):
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "error": str(exc), "rows": []}

            if result.get("ok"):
                return sql

            if attempt < 2:
                error = result.get("error", "Unknown SQLite error")
                previous_sql = sql
                sql = self._generate_sql(question, error, previous_sql)

        return sql

    def _generate_sql(self, question: str, error: str | None, previous_sql: str | None) -> str:
        prompt = self._build_prompt(question, error, previous_sql)
        system_prompt = (
            "You are an expert SQLite query writer. "
            "Given a database schema and a natural language question, "
            "produce a single SQLite SQL query that answers the question. "
            "Return only the SQL query without any explanation or markdown fences."
        )

        response = self.llm(prompt, system=system_prompt, temperature=0.0, n=1)
        text = self._response_to_text(response)
        sql = bridge.extract_sql(text)
        return sql if sql else text.strip()

    def _build_prompt(self, question: str, error: str | None, previous_sql: str | None) -> str:
        schema = getattr(self, "schema", None) or "No schema provided."

        parts = [
            "Database schema:",
            schema,
            "",
            f"Question: {question}",
        ]

        if previous_sql is not None:
            parts.extend([
                "",
                f"Previous SQL query:",
                previous_sql,
                "",
                f"SQLite error: {error}",
                "",
                "Please fix the SQL query so that it executes successfully and correctly answers the question.",
            ])
        else:
            parts.extend([
                "",
                "Write a SQLite query to answer the question.",
            ])

        return "\n".join(parts)

    @staticmethod
    def _response_to_text(response) -> str:
        if isinstance(response, list):
            return str(response[0]) if response else ""
        if isinstance(response, str):
            return response
        return str(response)