"""Generate SQL, execute it against the database, and on failure feed the exact SQLite error back to the LLM to regenerate the query, for up to two repair rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS1Repair(SQLHarness):
    """Weak-solver wrapper implementing a generate -> execute -> repair-on-error loop."""

    MAX_REPAIR_ROUNDS = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite assistant. Given a database schema and a "
        "question, write a single valid SQLite query that answers it. "
        "Output only the SQL inside a