"Repair loop: greedily generate SQL, execute it against the database, and feed any execution error back to the LLM for a corrected query (up to 3 attempts)."
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G4(SQLHarness):
    """Text-to-SQL harness that verifies candidate SQL by execution and
    repairs failures: each round the raw database error message from the
    failed attempt is appended to the prompt so the solver can regenerate
    a corrected query."""

    MAX_ATTEMPTS = 3

    SYSTEM = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "natural language question, output exactly one SQLite query that "
        "answers the question. Use only tables and columns that appear in the "
        "schema. Output only the SQL inside a