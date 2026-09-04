"""Repair-loop harness: generate SQL with the frozen solver, execute it against the database, and feed the engine's error messages back into the prompt for up to three corrective regeneration rounds."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G5(SQLHarness):
    """Text-to-SQL harness that self-repairs SQL using execution feedback.

    Control flow for every question:

    1. Ask the frozen solver for one SQLite ``SELECT`` statement.
    2. Execute that statement against the real database.
    3. If it executes cleanly, return it immediately.
    4. Otherwise record the failed SQL together with the exact engine error
       and regenerate, showing the solver the full failure history. This
       repair loop runs at most ``MAX_ROUNDS`` times.
    5. If every attempt fails, return the most recent extracted SELECT (the
       solver's best guess) so the caller still receives a query.
    """

    MAX_ROUNDS = 3  # initial generation + up to 3 error-driven repairs

    SYSTEM = (
        "You are a careful SQLite programmer. Given a database schema and a "
        "natural-language question, you write exactly one SQLite SELECT "
        "statement that answers it. You reply with a single