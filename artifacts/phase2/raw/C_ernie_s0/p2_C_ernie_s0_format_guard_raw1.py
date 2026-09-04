"""Generates SQL via LLM with strict format enforcement and one retry on execution failure."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS0FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: generate SQL with strict format instructions
        prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Provide ONLY the SQL query inside a