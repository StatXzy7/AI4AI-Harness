"""Uses error-driven repair: executes generated SQL and feeds execution errors back to the LLM for regeneration up to two repair attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS2G2(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL from question and schema
        prompt = f"Given the following database schema:\n\n{self.schema}\n\nWrite a SQL query to answer: {question}"
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)

        # Try execution with up to 2 repair attempts (3 total tries)
        for attempt in range(3):
            result = self.execute(sql)
            if result.get("ok", False):
                return sql

            # If failed, feed error back for repair
            error_msg = result.get("error", "Unknown error")
            repair_prompt = (
                f"The following SQL query failed with error: {error_msg}\n\n"
                f"Original question: {question}\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Fix the SQL query to resolve the error. Output only the corrected SQL."
            )
            repair_response = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(repair_response)

        return sql