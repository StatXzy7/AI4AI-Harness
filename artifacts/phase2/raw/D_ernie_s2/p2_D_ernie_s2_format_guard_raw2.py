"""A harness that wraps a frozen weak Text-to-SQL solver, enforcing output format and schema fidelity via prompt and extraction."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Construct a prompt emphasizing schema and format requirements
        prompt = (
            f"Given the following database schema:\n\n{self.schema}\n\n"
            f"Answer the question below by writing a SQL query.\n"
            f"Your response MUST contain ONLY the SQL query inside a