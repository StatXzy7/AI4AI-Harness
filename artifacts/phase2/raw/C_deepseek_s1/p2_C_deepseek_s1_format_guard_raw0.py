"""Generate schema-faithful SQL by enforcing strict fenced output and validating the query with execution feedback."""
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS1FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        system_prompt = (
            "You are a SQL generation assistant. "
            "You must output exactly one SQL query inside a