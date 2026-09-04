"""Repair harness that generates SQL, executes it, and retries up to two times with error feedback on failure."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS2Repair(SQLHarness):
    def solve(self, question: str) -> str:
        # Base prompt containing schema and question
        base_prompt = f"Given the following database schema:\n{self.schema}\n\nQuestion: {question}\n\nGenerate SQL to answer the question."
        prompt = base_prompt

        for attempt in range(3):
            # Generate SQL text using the frozen LLM
            response = self.llm(prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)

            # Execute the generated SQL
            result = self.execute(sql)
            if result["ok"]:
                return sql

            # If execution failed and retries remain, prepare feedback with the latest error
            if attempt < 2:
                error = result["error"]
                prompt = f"{base_prompt}\n\nPrevious attempt failed with error: {error}\n\nGenerate corrected SQL."

        # All attempts failed; return the last generated SQL
        return sql