"""Executes generated SQL, feeds back execution errors for regeneration, and returns a repaired query."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G1(SQLHarness):
    MAX_REPAIR_ATTEMPTS = 2

    def _call_llm(self, prompt, system=""):
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, list):
            response = response[0] if response else ""
        if isinstance(response, dict):
            response = (
                response.get("text")
                or response.get("output")
                or response.get("completion")
                or response.get("content")
                or ""
            )
        return response or ""

    def _generate_sql(self, prompt, system=""):
        text = self._call_llm(prompt, system=system)
        sql = bridge.extract_sql(text)
        return sql or text.strip()

    def _execute_sql(self, sql):
        try:
            return self.execute(sql)
        except Exception as exc:  # defensive: treat raised exceptions as execution failures
            return {"ok": False, "rows": [], "error": str(exc)}

    def solve(self, question: str) -> str:
        schema = self.schema

        initial_prompt = (
            "Given the following database schema, write a single SQL query that answers the user's question.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query."
        )

        sql = self._generate_sql(initial_prompt)
        if not sql:
            return ""

        result = self._execute_sql(sql)
        if result.get("ok"):
            return sql

        for _ in range(self.MAX_REPAIR_ATTEMPTS):
            error = result.get("error") or "Unknown execution error"
            repair_prompt = (
                "The following SQL query was generated for the question but produced an execution error.\n\n"
                f"Schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Execution error:\n{error}\n\n"
                "Write a corrected SQL query that fixes the error. Return only the SQL query."
            )

            sql = self._generate_sql(repair_prompt)
            if not sql:
                break

            result = self._execute_sql(sql)
            if result.get("ok"):
                return sql

        return sql