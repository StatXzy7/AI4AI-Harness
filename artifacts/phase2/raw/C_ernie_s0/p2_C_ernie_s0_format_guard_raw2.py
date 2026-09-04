"""Enforces strict SQL output format and schema fidelity through iterative extraction and execution validation with automatic correction on failure."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS0FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Initial prompt emphasizing schema and format constraints
        initial_prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Generate a SQL query that answers the question. "
            "You must output ONLY the SQL query inside a