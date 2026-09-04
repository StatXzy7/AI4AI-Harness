"""Harness that enforces strict SQL output format and schema adherence via prompt engineering and fence extraction."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Construct a prompt that emphasizes schema fidelity and output format
        prompt = (
            f"Given the following database schema:\n\n{self.schema}\n\n"
            f"Answer the following question: {question}\n\n"
            "Instructions:\n"
            "- Generate a SQL query that answers the question.\n"
            "- The query must strictly adhere to the provided schema (use exact table and column names).\n"
            "- Output ONLY the SQL query inside a