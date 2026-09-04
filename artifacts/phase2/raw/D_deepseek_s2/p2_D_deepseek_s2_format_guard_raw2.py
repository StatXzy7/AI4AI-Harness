"""Wraps a frozen text-to-SQL solver by enforcing fenced SQL output and iteratively correcting schema/execution errors through prompt feedback."""
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        last_sql = ""

        prompt = (
            "Use the schema below to answer the question with one valid SQL query.\n"
            "Return ONLY a SQL code block with no extra text, exactly like:\n"
            "