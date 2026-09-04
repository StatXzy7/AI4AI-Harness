"""Execute each generated SQL query and feed the database error message back to the frozen solver for up to three corrective regenerations."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G3(SQLHarness):
    """Draft-then-repair harness: one greedy generation, an execution check, then
    an error-feedback regeneration loop until the query executes or the budget
    of attempts is spent."""

    MAX_ATTEMPTS = 4         # 1 greedy draft + up to 3 error-feedback repairs
    RETRY_TEMPERATURE = 0.4  # used only when a repair repeats a known-bad query

    SYSTEM = (
        "You are an expert text-to-SQL engineer targeting SQLite. "
        "Use only the tables and columns that appear in the supplied schema, "
        "spell every identifier exactly as written there, and always answer with "
        "a single SELECT query inside one