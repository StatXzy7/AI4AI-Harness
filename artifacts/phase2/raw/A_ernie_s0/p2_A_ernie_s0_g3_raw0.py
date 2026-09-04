"""Repair mechanism: generate SQL, execute it, and if it fails, feed the error back for regeneration up to 3 attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        # Prompt the LLM to generate SQL from the question and schema
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nQuestion: {question}\n\nGenerate a valid SQL query that answers the question."
        system = "You are a SQL expert. Output only a valid SQL query, nothing else."

        max_attempts = 3
        for attempt in range(max_attempts):
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
            sql = bridge.extract_sql(response)

            # Execute the generated SQL
            result = self.execute(sql)

            if result.get("ok", False):
                return sql

            # If execution failed, append the error to the prompt for repair
            error_msg = result.get("error", "Unknown error")
            prompt = (
                f"Given the following database schema:\n\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"The following SQL query failed with error: {error_msg}\n\n"
                f"SQL: {sql}\n\n"
                f"Generate a corrected valid SQL query that answers the question."
            )

        # If all attempts fail, return the last generated SQL
        return sql