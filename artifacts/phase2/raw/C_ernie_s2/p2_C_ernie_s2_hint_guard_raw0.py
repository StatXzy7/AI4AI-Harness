"""Harness that parses Hint: constraints from the question and injects them as hard requirements into the prompt for a frozen weak Text-to-SQL solver."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Extract the hint line (if present) from the question
        hint = ""
        for line in question.splitlines():
            stripped = line.strip()
            if stripped.startswith("Hint:"):
                hint = stripped[len("Hint:"):].strip()
                break

        # Build the prompt with schema, question, and hard requirements from the hint
        prompt_parts = [
            f"Given the following database schema:\n\n{self.schema}\n\n",
            f"Question: {question}\n\n",
        ]
        if hint:
            prompt_parts.append(f"Hard requirements from hint: {hint}\n\n")
            prompt_parts.append("You must strictly follow these requirements when writing the SQL query.\n\n")
        prompt_parts.append("Write a SQL query that answers the question. Only output the SQL query.")
        prompt = "".join(prompt_parts)

        # Call the frozen weak solver (LLM) with temperature 0 for deterministic output
        response = self.llm(prompt, system="", temperature=0.0, n=1)

        # Extract the SQL from the LLM's response
        sql = bridge.extract_sql(response)

        return sql