"""Repair mechanism: generate an initial SQL query, execute it, and on errors feed the execution error back to the LLM for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2ADeepseekS0G7(SQLHarness):
    def solve(self, question: str) -> str:
        initial_prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query that answers the question."
        )

        response = self.llm(initial_prompt, temperature=0.0, n=1)
        sql = bridge.extract_sql(response)

        max_repairs = 3
        for _ in range(max_repairs):
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            error = result.get("error", "Unknown error")
            repair_prompt = (
                f"Given the following database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"The following SQL query was generated but failed to execute:\n{sql}\n\n"
                f"Execution error: {error}\n\n"
                "Please write a corrected SQL query that answers the question."
            )

            response = self.llm(repair_prompt, temperature=0.0, n=1)
            sql = bridge.extract_sql(response)

        return sql