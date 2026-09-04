"""Generate a candidate SQL query, execute it, and iteratively repair it using execution errors."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        base_prompt = (
            "Schema:\n"
            + self.schema
            + "\n\nQuestion: "
            + question
            + "\nWrite a SQL query that answers the question."
        )

        sql = ""
        current_prompt = base_prompt

        for _ in range(3):
            raw = self.llm(
                current_prompt,
                system="You are a SQL expert. Output only the SQL query.",
                temperature=0.0,
                n=1,
            )

            sql = bridge.extract_sql(raw)

            if not sql:
                current_prompt = (
                    base_prompt
                    + "\n\nYour previous response did not contain a SQL query. Please output only SQL."
                )
                continue

            result = self.execute(sql)

            if result["ok"]:
                return sql

            current_prompt = (
                base_prompt
                + "\n\nPrevious SQL:\n"
                + sql
                + "\n\nExecution error:\n"
                + str(result["error"])
                + "\n\nPlease fix the SQL query."
            )

        return sql