"""Repair mechanism: generate SQL, execute it, and use execution errors to fix it."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS1G0(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = self._make_prompt(question)
        response = self.llm(prompt, temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        if not sql:
            return ""

        max_attempts = 3
        for attempt in range(max_attempts):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            if attempt == max_attempts - 1:
                break

            error = result.get("error") or "Unknown execution error"
            repair_prompt = (
                f"{prompt}\n\n"
                f"Your previous SQL was:\n{sql}\n\n"
                f"Execution failed with error:\n{error}\n\n"
                "Please fix the SQL and output only the corrected SQL."
            )
            repair_response = self.llm(repair_prompt, temperature=0.0, n=1)
            repaired_sql = bridge.extract_sql(repair_response)
            if not repaired_sql:
                break
            sql = repaired_sql

        return sql

    def _make_prompt(self, question: str) -> str:
        return (
            "You are a SQL query generator. Write a SQL query that answers the user's question.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Output only the SQL query."
        )