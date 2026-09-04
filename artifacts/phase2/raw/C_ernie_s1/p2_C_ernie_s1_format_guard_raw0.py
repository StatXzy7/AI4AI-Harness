"""A harness that enforces strict SQL output formatting and schema fidelity via controlled LLM prompting and optional re-prompting on extraction or execution failure."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS1FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # First attempt: strict prompt emphasizing format and schema
        prompt = (
            f"Given the schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query that answers the question. "
            "You must output the query inside a