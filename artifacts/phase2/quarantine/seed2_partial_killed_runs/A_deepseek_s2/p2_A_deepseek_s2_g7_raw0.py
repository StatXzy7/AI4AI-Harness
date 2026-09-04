"""Repair-based Text-to-SQL: generate SQL, execute it, and ask the model to fix errors using execution feedback."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are a careful SQL expert. Return only SQL, no explanations."

        initial_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. Return only SQL."
        )

        sql = bridge.extract_sql(
            self.llm(initial_prompt, system=system, temperature=0.0, n=1)
        )

        for _ in range(3):
            if not sql:
                reprompt = (
                    f"Database schema:\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    "Your previous answer did not contain a SQL query. "
                    "Return only the SQL that answers the question."
                )
                sql = bridge.extract_sql(
                    self.llm(reprompt, system=system, temperature=0.0, n=1)
                )
                if not sql:
                    continue

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "Unknown execution error")
            repair_prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"The following SQL query produced an execution error:\n{sql}\n\n"
                f"Error message:\n{error}\n\n"
                "Write a corrected SQL query. Return only SQL, no explanations."
            )
            sql = bridge.extract_sql(
                self.llm(repair_prompt, system=system, temperature=0.0, n=1)
            )

        # Execute the final repaired SQL if it was generated after the last loop iteration.
        if sql:
            result = self.execute(sql)
            if result.get("ok"):
                return sql

        return sql or "SELECT 1;"