"""Harness that extracts a Hint: line from the question and includes it as a hard requirement in the prompt for a frozen LLM-based SQL generator."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Extract the hint line if present
        hint = ""
        for line in question.splitlines():
            stripped = line.strip()
            if stripped.startswith("Hint:"):
                hint = stripped[5:].strip()  # remove "Hint:" prefix
                break

        # Build the prompt with the schema and question
        prompt = f"""Given the following database schema:

{self.schema}

Write a SQL query to answer the question below.

Question: {question}

"""
        # Append the hint as a hard requirement if it exists
        if hint:
            prompt += f"""HARD REQUIREMENTS (from hint): {hint}
These constraints MUST be satisfied in the generated SQL query.

"""

        # Generate SQL using the frozen LLM (temperature=0.0, single sample)
        response = self.llm(prompt, system="", temperature=0.0, n=1)

        # Extract the SQL string from the LLM output
        sql = bridge.extract_sql(response)

        # Optional: execute to verify? Not required by the spec, but kept as a comment.
        # result = self.execute(sql)
        # if not result["ok"]:
        #     # In a real harness we might retry or handle error, but here we just return.
        #     pass

        return sql