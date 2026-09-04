"""Extracts and enforces Hint: constraints from the question as hard requirements before generating SQL via LLM."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Parse the hint line from the question
        lines = question.splitlines()
        hint_line = None
        cleaned_lines = []
        for line in lines:
            if line.strip().startswith("Hint:"):
                hint_line = line.strip()
            else:
                cleaned_lines.append(line)
        
        # Reconstruct question without hint line
        cleaned_question = "\n".join(cleaned_lines).strip()
        
        # Build prompt with schema, question, and hard-coded hint constraints
        prompt_parts = [
            "You are a Text-to-SQL expert. Given the database schema and question, write SQL.",
            "Schema:",
            self.schema,
            "",
            "Question:",
            cleaned_question,
        ]
        
        # Add hard requirements from hint if present
        if hint_line:
            hint_content = hint_line[len("Hint:"):].strip()
            prompt_parts.extend([
                "",
                "HARD REQUIREMENTS (must be strictly enforced in SQL):",
                hint_content,
            ])
        
        prompt = "\n".join(prompt_parts)
        
        # Generate SQL via frozen weak solver (LLM)
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        
        # Extract SQL from response
        final_sql = bridge.extract_sql(response)
        
        return final_sql