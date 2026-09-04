"""Repair mechanism: execute generated SQL and feed errors back for iterative correction."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BErnieS0G5(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL from schema + question
        prompt = f"""Given the following database schema:\n\n{self.schema}\n\nWrite a single SQL query that answers the question: {question}\n\nSQL:"""
        raw_text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw_text)

        # Try executing; if it fails, repair up to 2 times
        for attempt in range(3):
            result = self.execute(sql)
            if result.get("ok", False):
                return sql

            # Extract error message for repair prompt
            error_msg = result.get("error", "Unknown error")
            repair_prompt = f"""The following SQL query failed to execute with error:\n{error_msg}\n\nOriginal question: {question}\n\nDatabase schema:\n{self.schema}\n\nOriginal SQL:\n{sql}\n\nWrite a corrected SQL query that will execute successfully:"""
            raw_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(raw_text)

        # Return last attempt even if still failing
        return sql