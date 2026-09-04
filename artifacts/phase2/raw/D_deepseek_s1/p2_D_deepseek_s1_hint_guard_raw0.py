"""Parses the Hint line from the question and restates its constraints as hard SQL requirements before querying the LLM."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS1HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        hints = []
        for line in question.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("hint:"):
                hint = stripped.split(":", 1)[1].strip()
                if hint:
                    hints.append(hint)

        system_prompt = (
            "You are an expert Text-to-SQL assistant. "
            "Write a single SQL statement that answers the question."
        )
        user_prompt = f"Database schema:\n{self.schema}\n\nQuestion:\n{question}"

        if hints:
            hard_requirements = "\n".join(
                f"{i + 1}. {h}" for i, h in enumerate(hints)
            )
            system_prompt = (
                "You are an expert Text-to-SQL assistant. "
                "Before writing SQL, treat the following hard requirements extracted from the Hint as mandatory constraints. "
                "The final SQL must satisfy all of them."
            )
            user_prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Hard requirements (must all be satisfied):\n{hard_requirements}"
            )

        raw = self.llm(user_prompt, system=system_prompt, temperature=0.0, n=1)
        return bridge.extract_sql(raw)