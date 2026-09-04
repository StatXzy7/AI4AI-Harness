"""Repair-based Text-to-SQL harness that feeds execution errors back to the LLM to correct invalid SQL."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are an expert SQL engineer. Output only SQL, without any explanatory text."

        prompt = (
            "Given the following database schema and a natural language question, "
            "write a single SQL query that answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Output only the SQL query."
        )
        sql = bridge.extract_sql(self._unwrap(self.llm(prompt, system=system, temperature=0.0, n=1)))

        for _ in range(2):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "Unknown execution error")
            repair_prompt = (
                "The following SQL query was generated for the question, but it produced an execution error. "
                "Use the error message to fix the SQL.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Invalid SQL:\n{sql}\n\n"
                f"Execution error:\n{error}\n\n"
                "Output only the corrected SQL query."
            )
            sql = bridge.extract_sql(
                self._unwrap(self.llm(repair_prompt, system=system, temperature=0.0, n=1))
            )

        # Return the final SQL even if the last attempt still failed.
        return sql

    @staticmethod
    def _unwrap(response):
        if isinstance(response, list):
            return response[0] if response else ""
        if response is None:
            return ""
        return response