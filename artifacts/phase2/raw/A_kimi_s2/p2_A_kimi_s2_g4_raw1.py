"""Repair-loop harness: generate SQL, execute it, and feed any execution error back to the LLM for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G4(SQLHarness):
    """Text-to-SQL harness using an execution-feedback repair loop.

    Improvement over a single greedy call: the candidate SQL is actually
    executed against the database. If execution fails, the offending SQL
    and the database's error message are appended to the prompt and the
    model is asked to regenerate a corrected query. This repeats for a
    bounded number of attempts, returning the first query that executes
    successfully (or the final attempt if none succeed).
    """

    MAX_ATTEMPTS = 5

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL translator for SQLite databases. "
        "Given a database schema, a natural-language question, and possibly "
        "feedback about previous failed attempts, write exactly one correct "
        "SQLite query. Output only the SQL query inside a