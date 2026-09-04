"""Parses a Hint: line from the question and restates it as explicit hard requirements before requesting SQL generation."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2DDeepseekS0HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # 1. Parse the Hint: line from the question.
        hint = None
        clean_question = question
        for line in question.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("hint:"):
                hint = stripped[len("hint:"):].strip()
                clean_question = question.replace(line, "", 1).strip()
                break

        # 2. Build prompt with hard requirements explicitly included.
        prompt_parts = [
            f"Database schema:\n{self.schema}",
            f"Question:\n{clean_question}",
        ]
        if hint:
            prompt_parts.append(
                "Hard requirements parsed from the Hint line (obey these exactly):\n"
                f"- {hint}"
            )
        prompt_parts.append("Write only the SQL query.")

        prompt = "\n\n".join(part for part in prompt_parts if part)
        system = "You are a deterministic text-to-SQL assistant. Follow all hard requirements exactly."

        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(raw)