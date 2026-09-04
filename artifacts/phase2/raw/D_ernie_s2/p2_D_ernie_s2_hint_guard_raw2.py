"""This harness extracts and restates a 'Hint:' line from the question as hard constraints in the prompt to a frozen LLM for Text-to-SQL generation."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Parse the hint from the question
        hint_text = None
        question_lines = question.strip().split('\n')
        for i, line in enumerate(question_lines):
            if line.strip().startswith("Hint:"):
                hint_text = line.strip()[len("Hint:"):].strip()
                # Remove the hint line from the question for the LLM
                question_without_hint = '\n'.join(
                    question_lines[:i] + question_lines[i+1:]
                ).strip()
                break
        else:
            question_without_hint = question.strip()

        # Build prompt with hard requirements from hint
        prompt = f"Given the following database schema:\n{self.schema}\n\n"
        prompt += f"Answer the following question: {question_without_hint}\n"
        if hint_text:
            prompt += f"\nHARD REQUIREMENTS (must be satisfied): {hint_text}\n"
        prompt += "\nWrite a SQL query that satisfies all hard requirements and answers the question. Return only the SQL query."

        # Generate SQL with frozen LLM
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        
        # Extract SQL from response
        sql = bridge.extract_sql(response)
        
        return sql