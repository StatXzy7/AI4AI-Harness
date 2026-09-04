"""Repair-based solver that executes SQL and uses execution errors for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        sql = self._generate_sql(prompt)

        for _ in range(2):
            result = self._safe_execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "Unknown SQL execution error")
            repair_prompt = (
                f"{prompt}\n\n"
                f"Your previous SQL was:\n{sql}\n\n"
                f"That SQL produced an execution error:\n{error}\n\n"
                f"Please fix the SQL and return only the corrected SQL statement."
            )
            sql = self._generate_sql(repair_prompt) or sql

        return sql

    def _build_prompt(self, question: str) -> str:
        return (
            "You are an expert Text-to-SQL system. Use the provided database schema to "
            "answer the question by producing a single SQL query. Return only the SQL query, "
            "without explanation, markdown fences, or extra text.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n"
        )

    def _generate_sql(self, prompt: str) -> str:
        output = self.llm(prompt, temperature=0.0, n=1)
        if isinstance(output, list):
            if not output:
                return ""
            output = output[0]
        text = output if isinstance(output, str) else ""
        sql = bridge.extract_sql(text)
        if sql:
            return sql.strip()
        return text.strip()

    def _safe_execute(self, sql: str) -> dict:
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}