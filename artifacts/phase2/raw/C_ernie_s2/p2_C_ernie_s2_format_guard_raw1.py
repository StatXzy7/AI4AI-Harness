"""Harness that enforces strict SQL output format via prompt and extraction, wrapping a frozen LLM solver."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS2FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Build a prompt that strongly emphasizes format and schema fidelity
        prompt = (
            f"Given the following database schema:\n\n"
            f"{self.schema}\n\n"
            f"Answer the following question: {question}\n\n"
            f"Respond with ONLY a SQL query that answers the question. "
            f"The query must be enclosed in a