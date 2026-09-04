"""Generates SQL, executes it, and uses execution errors to repair the query before returning."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are a SQL expert. Return only SQL without explanation."

        def generate(prompt: str) -> str:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
            if response is None:
                return ""
            return bridge.extract_sql(str(response))

        prompt = (
            "Write a SQL query for the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query."
        )
        sql = generate(prompt)
        if not sql:
            sql = "SELECT 1"

        max_attempts = 3
        for attempt in range(max_attempts):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            if attempt == max_attempts - 1:
                break

            error = result.get("error") or "Unknown execution error"
            repair_prompt = (
                "The following SQL query failed to execute.\n"
                "Use the schema and error message to correct it.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Execution error:\n{error}\n\n"
                "Return only the corrected SQL query."
            )
            repaired = generate(repair_prompt)
            if not repaired:
                break
            sql = repaired

        return sql