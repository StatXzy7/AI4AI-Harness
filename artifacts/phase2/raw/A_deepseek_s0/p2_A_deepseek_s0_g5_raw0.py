"""Repair-based harness that retries SQL generation using execution error feedback."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS0G5(SQLHarness):
    def solve(self, question: str) -> str:
        system_prompt = "You are an expert Text-to-SQL assistant. Return only the SQL query."
        max_attempts = 3
        previous_sql = ""
        last_error = ""
        final_sql = ""

        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = (
                    f"Given the database schema:\n{self.schema}\n\n"
                    f"Write a SQL query for the following question:\n{question}\n\n"
                    "Return only the SQL query."
                )
            else:
                prompt = (
                    f"Given the database schema:\n{self.schema}\n\n"
                    f"Question:\n{question}\n\n"
                    f"Previous SQL query:\n{previous_sql}\n\n"
                    f"Execution error:\n{last_error}\n\n"
                    "Fix the SQL query and return only the corrected SQL."
                )

            raw = self.llm(prompt, system=system_prompt, temperature=0.0, n=1)
            if isinstance(raw, list):
                raw = raw[0] if raw else ""

            sql = bridge.extract_sql(raw).strip()
            if not sql:
                sql = raw.strip()

            final_sql = sql
            if not sql:
                previous_sql = ""
                last_error = "The model returned no SQL text."
                continue

            previous_sql = sql
            result = self.execute(sql)

            if result["ok"]:
                return sql

            last_error = result.get("error", "Unknown execution error")

        return final_sql