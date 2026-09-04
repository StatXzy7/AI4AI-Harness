"""Iteratively repairs SQL by executing generated queries and feeding execution errors back to the LLM for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS2G1(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial generation: produce SQL from question and schema
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nTranslate this question into a valid SQL query: {question}"
        sql_text = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_text)

        # Repair loop: execute, check, and regenerate on error
        max_attempts = 3
        for attempt in range(max_attempts):
            result = self.execute(sql)
            if result["ok"]:
                return sql

            # Construct repair prompt with error feedback
            error_msg = result.get("error", "Unknown execution error")
            repair_prompt = (
                f"Given the following database schema:\n\n{self.schema}\n\n"
                f"Original question: {question}\n\n"
                f"Previous SQL attempt: {sql}\n\n"
                f"The query failed with error: {error_msg}\n\n"
                f"Please generate a corrected SQL query that addresses this error."
            )
            sql_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_text)

        # Return the best (last) attempt even if still failing
        return sql