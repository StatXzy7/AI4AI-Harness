# MECHANISM: repair -- you execute SQL and feed execution errors back for regeneration
"""Repair-based harness that executes SQL and feeds execution errors back to the LLM for regeneration."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BMinimaxS1G4(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL from the question + schema
        initial_prompt = (
            f"Given the following database schema:\n\n{self.schema}\n\n"
            f"Write a SQL query that answers this question:\n{question}\n\n"
            f"Return only the SQL query, nothing else."
        )
        response = self.llm(initial_prompt, system="You are a SQL expert.", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)

        # Repair loop: execute, and if it fails, feed the error back
        max_repairs = 3
        for attempt in range(max_repairs):
            result = self.execute(sql)
            if result.get("ok", False):
                return sql

            # Build a repair prompt with the error information
            error = result.get("error", "unknown error")
            repair_prompt = (
                f"The following SQL query failed to execute:\n\n"
                f"{sql}\n\n"
                f"Error message:\n{error}\n\n"
                f"Original question:\n{question}\n\n"
                f"Database schema:\n{self.schema}\n\n"
                f"Please fix the SQL query so it executes correctly. "
                f"Return only the corrected SQL query."
            )
            response = self.llm(repair_prompt, system="You are a SQL expert.", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)

        # After max repairs, return the last attempt
        return sql