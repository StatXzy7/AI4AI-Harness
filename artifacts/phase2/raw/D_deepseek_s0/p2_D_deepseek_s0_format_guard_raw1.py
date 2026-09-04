"""Build a schema-grounded prompt that requires a single fenced SQL block and return only the SQL extracted by bridge.extract_sql, keeping no surrounding text."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS0FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "Translate the question into a single SQL query.\n"
            "Use only the tables and columns in the schema; do not invent names.\n"
            "The final answer must be exactly one SQL code block in this format, with no text before or after:\n\n"
            "