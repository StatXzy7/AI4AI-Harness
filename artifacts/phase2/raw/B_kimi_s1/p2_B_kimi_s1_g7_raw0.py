"""A repair-loop harness: generate SQL, execute it, and feed any database error back to the LLM so it can regenerate a corrected query, repeating until the query runs or the attempt budget is exhausted."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS1G7(SQLHarness):
    """Generates SQL, executes it, and iteratively repairs it using execution errors."""

    MAX_ATTEMPTS = 5

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL assistant. Given a database schema "
            "and a natural-language question, you write a single correct SQL "
            "query. You respond with only the SQL query inside a