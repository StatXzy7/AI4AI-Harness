"""Repair loop: execute generated SQL and, on error, feed the error back for a corrected SQL generation."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G2(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are a careful SQL expert. Return only SQL without explanation."

        sql = self._generate_initial_sql(question, system)

        for _ in range(2):
            result = self._execute_sql(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "Unknown execution error")
            repaired_response = self._repair_sql(question, sql, error, system)
            repaired_sql = bridge.extract_sql(repaired_response)

            if not repaired_sql:
                return sql

            sql = repaired_sql

        # Execute the final repaired SQL once more to check if it is valid.
        final_result = self._execute_sql(sql)
        if final_result.get("ok"):
            return sql

        return sql

    def _execute_sql(self, sql: str) -> dict:
        try:
            return self.execute(sql)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "rows": [], "error": str(exc)}

    def _generate_initial_sql(self, question: str, system: str) -> str:
        prompt = (
            "Write a SQL query for the following question.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query, with no extra commentary."
        )
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(response) or response.strip()

    def _repair_sql(self, question: str, previous_sql: str, error: str, system: str) -> str:
        prompt = (
            "A SQL query for the question failed with an execution error. "
            "Fix the SQL so it executes successfully and answers the question.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Previous SQL:\n{previous_sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Return only the corrected SQL query, with no extra commentary."
        )
        return self.llm(prompt, system=system, temperature=0.0, n=1)