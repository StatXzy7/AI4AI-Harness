# MECHANISM: repair
# Single-pass generation with execution-error feedback: parse, execute, and if execution fails, retry once with the error message inlined.
from __future__ import annotations
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G0(SQLHarness):
    """Single-prompt generation with one execution-guided repair retry on failure."""

    _SYSTEM = (
        "You are a precise Text-to-SQL generator. Given a natural language question and a "
        "database schema, output exactly one valid SQL query. Rules:\n"
        "- Return ONLY the SQL string, with no commentary, no markdown fences, no explanation.\n"
        "- Use only tables and columns that appear in the provided schema.\n"
        "- Prefer standard SQL; do not invent columns or tables.\n"
        "- If a column name contains spaces or reserved words, quote it appropriately.\n"
        "- Never wrap the output in