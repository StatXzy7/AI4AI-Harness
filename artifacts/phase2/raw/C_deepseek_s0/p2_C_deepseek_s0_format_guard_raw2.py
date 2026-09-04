"""Enforce SQL output inside a fenced block by prompting, repairing format failures, and validating against execution."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2CDeepseekS0FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        system_prompt = (
            "You are an expert SQL query generator. "
            "Given a database schema and a natural language question, produce the correct SQL query. "
            "Output ONLY a SQL query inside a markdown code fence: