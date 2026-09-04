"""Executes generated SQL, feeds execution errors back to the LLM, and returns a repaired query."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS0G2(SQLHarness):
    def solve(self, question: str) -> str:
        base_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query:"
        )

        sql = bridge.extract_sql(
            self.llm(
                base_prompt,
                system="You are a text-to-SQL assistant.",
                temperature=0.0,
                n=1,
            )
        )

        for _ in range(3):
            result = self.execute(sql)
            if result["ok"]:
                return sql

            error = result["error"]
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"The following SQL query was invalid:\n{sql}\n\n"
                f"Error:\n{error}\n\n"
                "Write a corrected SQL query:"
            )

            repaired_sql = bridge.extract_sql(
                self.llm(
                    repair_prompt,
                    system="You fix invalid SQL queries.",
                    temperature=0.0,
                    n=1,
                )
            )

            if repaired_sql:
                sql = repaired_sql

        return sql