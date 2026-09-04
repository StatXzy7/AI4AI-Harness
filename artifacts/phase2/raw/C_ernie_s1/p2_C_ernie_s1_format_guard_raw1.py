"""Wraps a frozen weak Text-to-SQL solver with strict format enforcement via prompt engineering and post-hoc extraction."""

from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS1FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # Construct a prompt that heavily emphasizes output format and schema fidelity
        system_prompt = (
            "You are a precise SQL generator. You must output ONLY the final SQL query "
            "inside a