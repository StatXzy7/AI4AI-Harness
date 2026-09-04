"""Repair-based Text-to-SQL harness that retries failed SQL using execution errors as feedback."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        base_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query that answers the question. Return only SQL."
        )
        prompt = base_prompt
        last_sql = ""

        for _ in range(3):
            response = self._generate(prompt)
            sql = bridge.extract_sql(response)
            if not sql:
                sql = response.strip()

            last_sql = sql

            if not sql:
                prompt = (
                    base_prompt
                    + "\n\nThe previous response contained no SQL. Please return only a SQL query."
                )
                continue

            try:
                result = self.execute(sql)
                if not isinstance(result, dict):
                    result = {}
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                return sql

            error = result.get("error", "unknown execution error")
            prompt = (
                base_prompt
                + f"\n\nPrevious SQL:\n{sql}\nExecution error: {error}\n"
                + "Fix the SQL so it executes successfully. Return only SQL."
            )

        return last_sql

    def _generate(self, prompt: str) -> str:
        response = self.llm(
            prompt,
            system="You are a precise SQL engineer. Return only SQL.",
            temperature=0.0,
            n=1,
        )
        if response is None:
            return ""
        if isinstance(response, (list, tuple)):
            return str(response[0]) if response else ""
        return str(response)