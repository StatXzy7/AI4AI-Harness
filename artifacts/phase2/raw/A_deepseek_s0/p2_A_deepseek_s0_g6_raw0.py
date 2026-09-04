"""Generate and execute an initial SQL query, then feed execution errors back to the LLM for targeted repair."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS0G6(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are a precise text-to-SQL assistant. Output only SQL without explanation."

        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question."
        )

        sql = bridge.extract_sql(
            self.llm(prompt, system=system, temperature=0.0, n=1)
        )

        for _ in range(2):
            if not sql:
                prompt = (
                    f"{prompt}\n\n"
                    "You did not output SQL. Output only the SQL query now."
                )
                sql = bridge.extract_sql(
                    self.llm(prompt, system=system, temperature=0.0, n=1)
                )
                continue

            result = self.execute(sql)

            if result["ok"]:
                return sql

            prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Your previous SQL was:\n{sql}\n\n"
                f"The database rejected it with this error:\n{result['error']}\n\n"
                "Output only the corrected SQL that fixes the error."
            )

            sql = bridge.extract_sql(
                self.llm(prompt, system=system, temperature=0.0, n=1)
            )

        return sql or ""