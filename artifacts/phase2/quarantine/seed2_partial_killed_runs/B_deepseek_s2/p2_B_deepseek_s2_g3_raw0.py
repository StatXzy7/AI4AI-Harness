"""Repair-based Text-to-SQL harness that re-prompts the LLM with execution errors until SQL executes or attempts are exhausted."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G3(SQLHarness):
    MAX_REPAIR_ATTEMPTS = 2

    def solve(self, question: str) -> str:
        sql = self._generate_sql(self._initial_prompt(question))
        if not sql:
            return ""

        for _ in range(self.MAX_REPAIR_ATTEMPTS):
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                return sql

            error = result.get("error") or "Unknown execution error"
            sql = self._generate_sql(self._repair_prompt(question, sql, error))
            if not sql:
                break

        return sql or ""

    def _generate_sql(self, prompt: str) -> str:
        raw = self.llm(
            prompt,
            system="You are an expert SQL writer. Output only a SQL query without explanation.",
            temperature=0.0,
            n=1,
        )
        extracted = bridge.extract_sql(raw)
        return extracted or raw.strip()

    def _initial_prompt(self, question: str) -> str:
        return (
            "Given the following database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question."
        )

    def _repair_prompt(self, question: str, previous_sql: str, error: str) -> str:
        return (
            "Given the following database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Your previous SQL query was:\n{previous_sql}\n\n"
            f"That query failed with the following error:\n{error}\n\n"
            "Write a corrected SQL query that answers the question."
        )