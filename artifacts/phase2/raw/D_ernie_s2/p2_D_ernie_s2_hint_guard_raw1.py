"""Parses Hint: constraints from the question and restates them as hard requirements in the LLM prompt before generating SQL."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Parse the Hint: line from the question
        hint_text = ""
        question_without_hint = question
        lines = question.split('\n')
        for i, line in enumerate(lines):
            if line.strip().startswith("Hint:"):
                hint_text = line.strip()[len("Hint:"):].strip()
                # Remove the hint line from the question to avoid confusion
                question_without_hint = '\n'.join(lines[:i] + lines[i+1:])
                break

        # Build the prompt with the hint restated as hard requirements
        if hint_text:
            prompt = (
                f"Given the database schema:\n{self.schema}\n\n"
                f"Question: {question_without_hint}\n\n"
                f"Hard requirements from hint: {hint_text}\n\n"
                f"Write a SQL query that answers the question and strictly satisfies the hard requirements above."
            )
        else:
            prompt = (
                f"Given the database schema:\n{self.schema}\n\n"
                f"Question: {question_without_hint}\n\n"
                f"Write a SQL query that answers the question."
            )

        # Generate SQL using the frozen LLM
        llm_output = self.llm(prompt, system="", temperature=0.0, n=1)
        
        # Extract SQL from the LLM output
        sql = bridge.extract_sql(llm_output)
        
        return sql