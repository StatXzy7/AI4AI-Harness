"""Repair SQL by executing it and feeding execution errors back to the LLM for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS0G7(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema or ""

        def _generate(prompt: str) -> str:
            response = self.llm(prompt, system="You are a SQL expert.", temperature=0.0, n=1)
            if isinstance(response, list):
                if not response:
                    return ""
                response = response[0]
            if response is None:
                return ""
            return str(response)

        initial_prompt = (
            "Given the following SQLite database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. "
            "Output only the SQL query, without any explanation or formatting."
        )

        raw = _generate(initial_prompt)
        sql = bridge.extract_sql(raw) or raw.strip()

        for attempt in range(3):
            if not sql:
                break

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "Unknown execution error")
            if attempt == 2:
                break

            repair_prompt = (
                "The following SQL query executed against SQLite and produced an error:\n"
                f"{sql}\n\n"
                f"Error: {error}\n\n"
                "Database schema:\n"
                f"{schema}\n\n"
                f"Question: {question}\n\n"
                "Write a corrected SQL query. "
                "Output only the SQL query, without any explanation or formatting."
            )

            raw = _generate(repair_prompt)
            sql = bridge.extract_sql(raw) or raw.strip()

        if sql:
            return sql
        return raw.strip() if raw else ""