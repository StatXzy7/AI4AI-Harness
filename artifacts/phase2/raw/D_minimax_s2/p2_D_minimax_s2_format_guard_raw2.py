"""P2P2DMinimaxS2FormatGuard: wraps a frozen weak Text-to-SQL solver by enforcing strict output format and schema fidelity through structured prompting and post-generation fence extraction."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        system_prompt = (
            "You are a precise Text-to-SQL generator.\n"
            "STRICT OUTPUT FORMAT RULES:\n"
            "1. You MUST output exactly one SQL query.\n"
            "2. The SQL query MUST be enclosed in a