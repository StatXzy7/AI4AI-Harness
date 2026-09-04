"""Forces the LLM to output only a fenced SQL block and extracts it with bridge.extract_sql."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        system_prompt = (
            "You are a precise text-to-SQL translator. "
            "Use only the database schema provided below. "
            "Output exactly one SQL query inside a