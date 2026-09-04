"""This harness uses iterative repair: it executes generated SQL and feeds execution errors back to the LLM for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AErnieS2G5(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        for attempt in range(max_attempts):
            prompt = f"Given the schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate a valid SQL query."
            raw = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(raw)

            result = self.execute(sql)
            if result["ok"]:
                return sql

            # Feed the error back for repair on the next attempt
            error_feedback = f"The previous SQL query failed with error: {result['error']}\nPlease generate a corrected SQL query."
            if attempt == max_attempts - 1:
                # Last attempt: include the error feedback in the prompt
                prompt = f"Given the schema:\n{self.schema}\n\nQuestion: {question}\n\n{error_feedback}"
                raw = self.llm(prompt, system="", temperature=0.0, n=1)
                return bridge.extract_sql(raw)
            else:
                prompt = f"Given the schema:\n{self.schema}\n\nQuestion: {question}\n\n{error_feedback}"

        # Fallback: return last generated SQL even if it failed
        return sql