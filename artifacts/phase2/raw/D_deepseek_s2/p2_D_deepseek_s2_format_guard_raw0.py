"""Enforces fenced SQL output from Deepseek by prompting, extracting, and retrying on format failures."""
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        system_prompt = (
            "You are a text-to-SQL assistant. "
            "Your entire response must be a single SQL query inside a