"""Generates a SQL query, executes it, and uses execution errors to prompt the LLM for a repaired query."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        def _generate_sql(prompt: str) -> str:
            raw = self.llm(prompt, system="", temperature=0.0, n=1)
            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            return bridge.extract_sql(raw or "")

        def _execute_safe(sql: str) -> dict:
            try:
                return self.execute(sql)
            except Exception as exc:  # pragma: no cover - defensive
                return {"ok": False, "error": str(exc)}

        schema = self.schema

        initial_prompt = (
            f"Given the following database schema:\n{schema}\n\n"
            f"Write a SQL query for this question:\n{question}\n\n"
            "Output only the SQL query."
        )

        sql = _generate_sql(initial_prompt)

        for _ in range(2):
            if not sql:
                break

            result = _execute_safe(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "Unknown execution error")
            repair_prompt = (
                f"Given the following database schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                f"The SQL query below was generated but failed to execute:\n{sql}\n\n"
                f"Execution error:\n{error}\n\n"
                "Fix the SQL query. Output only the corrected SQL query."
            )

            new_sql = _generate_sql(repair_prompt)
            if not new_sql:
                break

            sql = new_sql

        return sql or ""