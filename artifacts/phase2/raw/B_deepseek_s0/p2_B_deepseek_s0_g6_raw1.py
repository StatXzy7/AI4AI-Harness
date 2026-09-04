"""Iteratively generate SQL and, when execution fails, feed the error back to the model for repair."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS0G6(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        system = "You are an expert Text-to-SQL assistant. Output only SQL."
        base_prompt = (
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query to answer the question."
        )
        max_attempts = 3
        last_sql = ""

        prompt = base_prompt
        for _ in range(max_attempts):
            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            sql = bridge.extract_sql(raw)

            if not sql:
                prompt = (
                    "Your previous answer did not contain a SQL query. "
                    "Output only the SQL query, no explanation.\n\n" + base_prompt
                )
                continue

            last_sql = sql
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            error = result.get("error") or "Unknown execution error"
            prompt = (
                f"Database schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                f"Your previous SQL was:\n{sql}\n\n"
                f"The SQL execution failed with the following error:\n{error}\n\n"
                "Output only a corrected SQL query that fixes this error."
            )

        return last_sql