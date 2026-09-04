"""Repair-loop Text-to-SQL harness: generate SQL, execute it, and feed database errors back to the frozen solver for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G0(SQLHarness):
    """Generate -> execute -> on failure, feed the DB error back and regenerate.

    The frozen solver is wrapped in a bounded repair loop. Each candidate SQL
    string is executed against the database; if execution fails, the error
    message and the offending query are placed into a repair prompt and the
    solver is asked to produce a corrected query. Because the solver is run at
    temperature 0.0, the loop stops early when the model repeats itself (an
    identical repair prompt would deterministically yield the identical reply).
    """

    MAX_ATTEMPTS = 3

    SYSTEM = (
        "You are an expert Text-to-SQL engine. Given a database schema and a "
        "natural-language question, respond with exactly one SQL query inside a "
        "