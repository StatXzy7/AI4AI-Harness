"""Harness that parses a 'Hint:' line from the question and enforces its constraints as hard requirements when generating SQL via LLM."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Parse the hint line (case-insensitive) from the question
        hint = ""
        for line in question.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("hint:"):
                hint = stripped
                break

        # Step 2: Build the initial prompt that includes the hint as a hard requirement
        prompt = (
            f"Given the schema: {self.schema}\n\n"
            f"Question: {question}\n\n"
            f"{hint}\n\n"
            "Write a SQL query that answers the question and satisfies the hint. "
            "Only output the SQL query."
        )

        # Step 3: Generate SQL with the LLM
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)

        # Step 4: Execute the generated SQL
        result = self.execute(sql)
        if result["ok"] and result["rows"]:
            return sql

        # Step 5: Retry up to two more times with an even stronger emphasis on the hint
        for _ in range(2):
            retry_prompt = (
                f"Given the schema: {self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Hint: {hint}\n\n"
                "You MUST satisfy the hint. Write a SQL query that answers the question "
                "and satisfies the hint. Only output the SQL query."
            )
            response = self.llm(retry_prompt, system="", temperature=0.0, n=1)
            sql = bridge.extract_sql(response)
            result = self.execute(sql)
            if result["ok"] and result["rows"]:
                return sql

        # If all attempts fail, return the last generated SQL (may be invalid)
        return sql