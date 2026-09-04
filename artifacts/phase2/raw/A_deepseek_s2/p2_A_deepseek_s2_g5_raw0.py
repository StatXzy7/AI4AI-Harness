"""Repair mechanism: execute generated SQL and feed execution errors back to the LLM for iterative regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G5(SQLHarness):
    def solve(self, question: str) -> str:
        sql = ""
        last_sql = None
        last_error = ""

        for attempt in range(3):
            if attempt == 0:
                prompt = (
                    "You are an expert SQL developer. Write a single SQL query that answers the question.\n\n"
                    f"Schema:\n{self.schema}\n\n"
                    f"Question:\n{question}\n\n"
                    "Return only the SQL query."
                )
            else:
                prompt = (
                    "Your previous SQL query produced an error. Fix the query.\n\n"
                    f"Schema:\n{self.schema}\n\n"
                    f"Question:\n{question}\n\n"
                    f"Previous SQL:\n{last_sql}\n\n"
                    f"Error:\n{last_error}\n\n"
                    "Return only the corrected SQL query."
                )

            raw = self._call_llm(prompt)
            sql = bridge.extract_sql(raw)
            if not sql:
                continue

            if sql == last_sql:
                continue

            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                return sql

            last_sql = sql
            last_error = result.get("error", "Unknown execution error")

        return sql

    def _call_llm(self, prompt: str) -> str:
        raw = self.llm(prompt, system="You are a helpful SQL expert.", temperature=0.0, n=1)
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        if isinstance(raw, dict):
            raw = raw.get("text") or raw.get("message") or raw.get("content") or ""
        return str(raw)