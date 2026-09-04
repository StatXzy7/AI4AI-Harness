"""Harness that enforces strict SQL output format via prompt engineering and post-extraction validation to ensure schema fidelity."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS2FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Construct prompt with explicit format constraints and schema context
        prompt = (
            f"Given the following database schema:\n\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write the SQL query to answer the question. "
            f"You MUST output ONLY the SQL query inside a