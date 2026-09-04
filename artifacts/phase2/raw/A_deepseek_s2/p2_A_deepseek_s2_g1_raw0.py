"""This harness iteratively repairs SQL by executing it and feeding the resulting error back to the LLM."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G1(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 4

        def _call_llm(prompt: str) -> str:
            response = self.llm(prompt, temperature=0.0, n=1)
            if isinstance(response, list):
                return response[0] if response else ""
            return response or ""

        def _initial_prompt() -> str:
            return (
                "Given the following SQLite schema:\n"
                f"{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Write a single SQL query that answers the question. Return only the SQL."
            )

        raw = _call_llm(_initial_prompt())
        sql = bridge.extract_sql(raw) or raw.strip()
        last_sql = None

        for _ in range(max_attempts):
            if sql == last_sql:
                break
            last_sql = sql

            try:
                result = self.execute(sql)
            except Exception as exc:  # noqa: BLE001 - keep repair loop alive on unexpected errors
                result = {"ok": False, "error": str(exc), "rows": []}

            if result.get("ok"):
                return sql

            error = result.get("error") or "Unknown execution error"
            repair_prompt = (
                "You previously generated this SQL:\n"
                f"{sql}\n\n"
                "It produced the following execution error:\n"
                f"{error}\n\n"
                "Schema:\n"
                f"{self.schema}\n\n"
                f"Question: {question}\n\n"
                "Write a corrected SQL query. Return only the SQL."
            )
            raw = _call_llm(repair_prompt)
            sql = bridge.extract_sql(raw) or raw.strip()

        return sql