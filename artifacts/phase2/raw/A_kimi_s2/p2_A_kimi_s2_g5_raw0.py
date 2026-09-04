"""Iteratively generate SQL, execute it, and feed execution errors back to the LLM so it can repair the query."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G5(SQLHarness):
    """Repair-loop harness: draft SQL, run it, and regenerate with the
    execution error in context until the query succeeds or the attempt
    budget is exhausted."""

    MAX_ATTEMPTS = 4

    SYSTEM = (
        "You are an expert Text-to-SQL translator. Given a database schema "
        "and a natural-language question, produce one syntactically valid SQL "
        "query that answers the question. Output only the SQL, wrapped in a "
        "