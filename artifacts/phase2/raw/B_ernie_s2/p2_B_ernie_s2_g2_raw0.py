"""Iteratively repairs SQL queries by executing each attempt and feeding execution errors back to the LLM for regeneration up to 3 attempts."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BErnieS2G2(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        last_sql = None

        for attempt in range(max_attempts):
            if attempt == 0:
                prompt = (
                    f"Given the following database schema:\n\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Write a SQL query that answers the question."
                )
            else:
                error_msg = result.get("error", "Unknown error")
                prompt = (
                    f"Given the following database schema:\n\n{self.schema}\n\n"
                    f"Question: {question}\n\n"
                    f"Your previous SQL query failed with this error:\n{error_msg}\n\n"
                    f"Previous SQL:\n{last_sql}\n\n"
                    f"Write a corrected SQL query that answers the question."
                )

            sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_text)
            last_sql = sql

            result = self.execute(sql)

            if result.get("ok"):
                return sql

        return last_sql