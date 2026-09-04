# MECHANISM: repair
"""Harness that repairs SQL by feeding execution errors back to the LLM for regeneration."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS1G3(SQLHarness):
    def solve(self, question: str) -> str:
        # First greedy attempt
        prompt = (
            "You are a SQL expert. Given the schema and a natural language question, "
            "produce a single executable SQLite SQL query that answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return ONLY the SQL statement, with no prose and no markdown fences."
        )
        text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(text)

        # Attempt to execute; if it fails, feed error back for repair.
        max_attempts = 3
        for attempt in range(max_attempts):
            result = self.execute(sql)
            if result.get("ok", False):
                return sql

            err = result.get("error", "unknown error")
            repair_prompt = (
                "The following SQL query failed to execute against the database. "
                "Repair it so it executes correctly and answers the original question.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Original Question: {question}\n\n"
                f"Original SQL:\n{sql}\n\n"
                f"Execution Error:\n{err}\n\n"
                "Return ONLY the corrected SQL statement, with no prose and no markdown fences."
            )
            text2 = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            new_sql = bridge.extract_sql(text2)
            if not new_sql:
                # Extraction failed; keep current sql and try again
                continue
            sql = new_sql

        # Return best-effort SQL after exhausting repairs
        return sql