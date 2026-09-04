"""Repair-based Text-to-SQL solver that feeds execution errors back to the LLM for corrected regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS1G2(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = self._build_initial_prompt(question)
        sql = bridge.extract_sql(self.llm(prompt))

        for _ in range(3):
            if not sql:
                prompt = self._build_repair_prompt(
                    question, sql, "No SQL query could be extracted from the previous response."
                )
                sql = bridge.extract_sql(self.llm(prompt))
                continue

            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if result.get("ok"):
                return sql

            error = str(result.get("error") or "Unknown execution error")
            prompt = self._build_repair_prompt(question, sql, error)
            sql = bridge.extract_sql(self.llm(prompt))

        return sql or ""

    def _build_initial_prompt(self, question: str) -> str:
        return (
            "You are a SQL expert. Given the database schema below, write a single SQLite query "
            "that answers the user question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Respond with the SQL query only."
        )

    def _build_repair_prompt(self, question: str, previous_sql: str, error: str) -> str:
        return (
            "The following SQL query was generated for the question, but it failed to execute.\n"
            f"Question: {question}\n"
            f"Schema:\n{self.schema}\n"
            f"Previous SQL:\n{previous_sql}\n"
            f"Execution error:\n{error}\n\n"
            "Write a corrected SQLite query. Respond with the SQL query only."
        )