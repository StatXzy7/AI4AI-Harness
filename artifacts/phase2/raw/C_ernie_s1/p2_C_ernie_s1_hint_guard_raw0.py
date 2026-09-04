"""Parse a 'Hint:' line from the question, restate its constraints as hard requirements, and generate SQL via a frozen LLM."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS1HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Extract the hint line (if present) and remove it from the question
        lines = question.split('\n')
        hint_line = None
        question_lines = []
        for line in lines:
            if line.startswith('Hint:'):
                hint_line = line
            else:
                question_lines.append(line)
        question_without_hint = '\n'.join(question_lines).strip()
        hint_text = hint_line[len('Hint:'):].strip() if hint_line else None

        # Step 2: Build the prompt with schema, question, and explicit hint constraints
        prompt = f"Schema: {self.schema}\n\n"
        prompt += f"Question: {question_without_hint}\n\n"
        if hint_text:
            prompt += f"Hint constraints (must be satisfied): {hint_text}\n\n"
        prompt += "Write a single SQL query that answers the question and satisfies all given constraints."

        # Step 3: Generate SQL using the frozen LLM (temperature=0, n=1)
        response = self.llm(prompt, system="", temperature=0.0, n=1)

        # Step 4: Extract the SQL string from the LLM output
        final_sql = bridge.extract_sql(response)

        return final_sql