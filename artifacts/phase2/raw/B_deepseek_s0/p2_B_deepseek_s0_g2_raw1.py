"""Repair-based Text-to-SQL: generate SQL, execute it, and feed execution errors back for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS0G2(SQLHarness):
    def _execute_safely(self, sql: str) -> dict:
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    def _generate(self, prompt: str) -> str:
        system = (
            "You are a SQL expert. Write a single SQL query to answer "
            "the user's question. Do not explain."
        )
        return self.llm(prompt, system=system, temperature=0.0)

    def solve(self, question: str) -> str:
        schema = self.schema
        prompt = (
            f"Question: {question}\n"
            f"Schema:\n{schema}\n"
            "Write a SQL query to answer the question."
        )
        raw = self._generate(prompt)
        sql = bridge.extract_sql(raw)
        result = None

        if sql:
            result = self._execute_safely(sql)
            if result.get("ok"):
                return sql

        for _ in range(2):
            if sql:
                error = result.get("error", "Unknown error") if result else "Unknown error"
                prompt = (
                    f"Your previous SQL query failed.\n"
                    f"Question: {question}\n"
                    f"Schema:\n{schema}\n"
                    f"Previous SQL:\n{sql}\n"
                    f"Execution error:\n{error}\n"
                    "Write a corrected SQL query to answer the question."
                )
            else:
                prompt = (
                    f"Your previous answer did not contain a SQL query.\n"
                    f"Question: {question}\n"
                    f"Schema:\n{schema}\n"
                    "Write a SQL query to answer the question."
                )
            raw = self._generate(prompt)
            sql = bridge.extract_sql(raw)
            if sql:
                result = self._execute_safely(sql)
                if result.get("ok"):
                    return sql

        return sql or ""