"""Repair-loop Text-to-SQL harness that executes each candidate query and feeds execution errors back to the LLM for correction."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G2(SQLHarness):
    """Generate -> execute -> repair loop around the frozen solver LLM.

    A single greedy call is replaced by a bounded feedback loop:
    each generated query is executed against the database; on error
    (or a suspicious zero-row result) the failure is appended to a
    history that is handed back to the model, which must diagnose the
    mistake and emit a corrected query. Previously tried queries are
    remembered so identical failures are never re-executed.
    """

    MAX_ATTEMPTS = 4

    SYSTEM = (
        "You are an expert Text-to-SQL engine. Given a database schema and "
        "a natural-language question, you output exactly one SQL query that "
        "answers the question, wrapped in a