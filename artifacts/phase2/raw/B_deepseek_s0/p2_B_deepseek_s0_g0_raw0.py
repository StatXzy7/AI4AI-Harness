"""Iteratively repair generated SQL by executing it and feeding execution errors back to the LLM."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        base_prompt = (
            f"Given the following database schema:\n{schema}\n\n"
            f"Write a SQL query to answer the question: {question}\n"
            "Return only the SQL query."
        )

        first_response = self._call_llm(base_prompt)
        last_sql = self._extract_sql(first_response)

        for _ in range(2):
            result = self.execute(last_sql)
            if result.get("ok"):
                return last_sql

            error_msg = result.get("error", "unknown execution error")
            repair_prompt = (
                f"Database schema:\n{schema}\n\n"
                f"Question: {question}\n\n"
                f"Your previous SQL query was:\n{last_sql}\n\n"
                f"It failed with the following error:\n{error_msg}\n\n"
                "Please write a corrected SQL query that answers the question. "
                "Return only the SQL query."
            )

            repaired_response = self._call_llm(repair_prompt)
            repaired_sql = self._extract_sql(repaired_response)

            if not repaired_sql:
                repaired_sql = last_sql

            last_sql = repaired_sql

        return last_sql

    def _call_llm(self, prompt: str) -> str:
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        if isinstance(response, list):
            return response[0].strip() if response else ""
        return response.strip()

    @staticmethod
    def _extract_sql(text: str) -> str:
        sql = bridge.extract_sql(text).strip()
        if sql:
            return sql
        return text.strip()