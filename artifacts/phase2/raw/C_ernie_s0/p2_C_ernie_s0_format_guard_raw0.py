"""A harness that enforces SQL output format and schema fidelity via retry loop with error feedback and strict prompt."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS0FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        system_prompt = "You are a SQL expert. You must output ONLY the SQL query inside a