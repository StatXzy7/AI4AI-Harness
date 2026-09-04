"""Repair-based Text-to-SQL solver that feeds execution errors back to the model for iterative correction."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS1G0(SQLHarness):
    """Repair-based harness for Text-to-SQL."""

    def solve(self, question: str) -> str:
        max_attempts = 3
        prompt = self._build_initial_prompt(question)
        sql = ""

        for attempt in range(1, max_attempts + 1):
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)

            if not sql:
                error = "The model did not produce a SQL query."
                previous = response or ""
                if attempt < max_attempts:
                    prompt = self._build_repair_prompt(question, previous, error)
                continue

            result = self.execute(sql)

            if result.get("ok"):
                return sql

            if attempt < max_attempts:
                error = result.get("error", "Unknown error")
                prompt = self._build_repair_prompt(question, sql, error)

        return sql or ""

    def _build_initial_prompt(self, question: str) -> str:
        return (
            "Given the following database schema:\n"
            f"{self.schema}\n\n"
            f"Write a SQL query to answer the following question:\n{question}\n\n"
            "Return only the SQL query."
        )

    def _build_repair_prompt(self, question: str, sql: str, error: str) -> str:
        return (
            "Given the following database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "The following SQL query was generated but produced an error:\n"
            f"{sql}\n\n"
            f"Error: {error}\n\n"
            "Fix the SQL query. Return only the corrected SQL query."
        )