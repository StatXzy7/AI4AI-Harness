"""Harness that extracts and enforces a Hint constraint as a hard requirement before generating SQL."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS0HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Parse hint lines from the question
        lines = question.splitlines()
        hint_parts = []
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Hint:"):
                # Extract the hint text after "Hint:"
                hint_text = stripped[len("Hint:"):].strip()
                if hint_text:
                    hint_parts.append(hint_text)
            else:
                cleaned_lines.append(line)
        # Combine multiple hints into one requirement (if any)
        hint_requirement = ""
        if hint_parts:
            hint_requirement = " ".join(hint_parts)
        # Build the cleaned question (without hint lines)
        cleaned_question = "\n".join(cleaned_lines)
        # Construct prompt with schema, cleaned question, and hard requirement
        prompt = f"Given the database schema:\n{self.schema}\n\n"
        prompt += f"Question: {cleaned_question}\n\n"
        if hint_requirement:
            prompt += f"Hard requirement: {hint_requirement}. The SQL query must satisfy this requirement.\n\n"
        prompt += "Write a SQL query that answers the question and satisfies the hard requirement."
        # Call the frozen LLM solver
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        # Extract SQL from the response
        sql = bridge.extract_sql(response)
        return sql