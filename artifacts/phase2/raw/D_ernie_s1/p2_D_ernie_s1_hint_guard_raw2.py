"""Parse the Hint: line from the question, restate it as hard constraints in the prompt, then generate SQL via a frozen LLM."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS1HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Split the question into lines and extract the Hint: line
        lines = question.strip().split('\n')
        hint = None
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('Hint:'):
                hint = stripped
            else:
                cleaned_lines.append(line)
        question_text = '\n'.join(cleaned_lines).strip()

        # Build the prompt with the schema, cleaned question, and hard requirement from hint
        prompt = f"Given the following database schema:\n{self.schema}\n\n"
        prompt += f"Question: {question_text}\n"
        if hint:
            prompt += f"Hard requirement: {hint}. Your SQL query must satisfy this constraint.\n"
        prompt += "Write a single SQL query that answers the question and satisfies all constraints."

        # Generate SQL using the frozen LLM
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        return sql