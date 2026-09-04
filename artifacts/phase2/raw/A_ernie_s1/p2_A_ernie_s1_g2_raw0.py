"""Iterative repair mechanism that executes generated SQL and feeds execution errors back to the LLM for regeneration up to a fixed retry limit."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS1G2(SQLHarness):
    def solve(self, question: str) -> str:
        # Build the initial prompt with schema and question
        prompt = f"{self.schema}\n\nQuestion: {question}\n\nSQL:"
        system = "You are a SQL expert. Write a single valid SQL query that answers the question. Output only the SQL query, no explanations."

        max_retries = 3
        last_sql = None

        for attempt in range(max_retries):
            # Greedy generation call
            raw_text = self.llm(prompt, system=system, temperature=0.0, n=1)
            candidate_sql = bridge.extract_sql(raw_text)

            if candidate_sql is None or candidate_sql.strip() == "":
                # If extraction failed, treat as empty and retry
                candidate_sql = ""

            # Execute the candidate SQL
            result = self.execute(candidate_sql)

            if result.get("ok", False):
                # Success: return the working SQL
                return candidate_sql

            # Failure: collect error info and prepare for repair
            error_msg = result.get("error", "Unknown execution error")
            last_sql = candidate_sql

            # Build repair prompt that includes the previous attempt and the error
            repair_prompt = (
                f"{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Your previous SQL query was:\n{last_sql}\n\n"
                f"The database returned this error:\n{error_msg}\n\n"
                f"Write a corrected SQL query that fixes the error. Output only the SQL query."
            )

            # Use the repair prompt for the next iteration
            prompt = repair_prompt

        # If all retries exhausted, return the last attempt (best effort)
        return last_sql if last_sql is not None else ""