"""Generate a SQL query and repair it against execution errors until it runs successfully."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS1G5(SQLHarness):
    def solve(self, question: str) -> str:
        # First greedy attempt
        sql = self._generate_sql(self._make_initial_prompt(question))
        result = self._safe_execute(sql)

        if result.get("ok"):
            return sql

        # Repair attempts using execution error feedback
        previous_sql = sql
        error = result.get("error", "Unknown error")
        for _ in range(2):
            sql = self._generate_sql(
                self._make_repair_prompt(question, previous_sql, error)
            )
            result = self._safe_execute(sql)
            if result.get("ok"):
                return sql
            previous_sql = sql
            error = result.get("error", "Unknown error")

        return sql

    def _generate_sql(self, prompt: str) -> str:
        raw = self.llm(prompt, system="", temperature=0.0, n=1)
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        raw = raw or ""
        sql = bridge.extract_sql(raw)
        if not sql:
            sql = raw.strip()
        return sql

    def _safe_execute(self, sql: str) -> dict:
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    def _make_initial_prompt(self, question: str) -> str:
        return (
            "You are an expert SQL writer.\n"
            "Given the following database schema:\n"
            f"{self.schema}\n\n"
            "Write a single SQL query that answers the user's question.\n"
            f"Question: {question}\n"
            "Return only the SQL query, without explanation."
        )

    def _make_repair_prompt(self, question: str, previous_sql: str, error: str) -> str:
        return (
            "You are an expert SQL writer.\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Your previous SQL query was:\n"
            f"{previous_sql}\n\n"
            "It failed to execute with the following error:\n"
            f"{error}\n\n"
            "Fix the SQL query. Return only the corrected SQL query, without explanation."
        )