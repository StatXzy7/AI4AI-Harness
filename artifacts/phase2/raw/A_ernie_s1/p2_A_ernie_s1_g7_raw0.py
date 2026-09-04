"""This harness uses a repair mechanism: it generates SQL, executes it, and if there's an error, it feeds the error back to the LLM for regeneration up to a fixed number of attempts."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

class P2P2AErnieS1G7(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3
        schema = self.schema
        # Initial prompt for the first attempt
        prompt = f"Schema: {schema}\nQuestion: {question}\nGenerate SQL:"
        last_sql = ""
        for attempt in range(max_attempts):
            # Generate a single sample (greedy) from the LLM
            text = self.llm(prompt, system="", temperature=0.0, n=1)
            # Extract SQL from the generated text
            sql = bridge.extract_sql(text)
            if not sql:
                # Fallback: use the raw text if extraction fails
                sql = text.strip()
            last_sql = sql
            # Execute the generated SQL
            result = self.execute(sql)
            if result.get("ok", False):
                return sql
            # If execution failed, prepare a repair prompt with the error
            error = result.get("error", "Unknown error")
            prompt = f"Schema: {schema}\nQuestion: {question}\nPrevious SQL: {sql}\nError: {error}\nFix the SQL:"
        # If all attempts fail, return the last generated SQL
        return last_sql