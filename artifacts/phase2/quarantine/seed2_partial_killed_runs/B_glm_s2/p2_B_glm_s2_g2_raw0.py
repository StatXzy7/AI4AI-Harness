"""Repair-loop harness: greedy SQL generation followed by execution on the frozen database, with each execution error fed back to the LLM for up to two corrective regeneration rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G2(SQLHarness):
    """Greedy first shot + execution-error-driven repair loop.

    Control flow (a real change over a single greedy call):

        1. Ask the LLM once (temperature 0.0) for a SQL query.
        2. Execute that query on the real database via self.execute().
        3. If it executes cleanly -> return it.
        4. If it fails (or no SQL could be extracted), append (sql, error)
           to a history and re-prompt the LLM with the schema, the question,
           every failed SQL and its *actual* database error message, asking
           for a corrected query.
        5. Repeat up to MAX_REPAIRS times, bumping temperature on the last
           repair so the model can escape a deterministic failure mode.
        6. If everything still fails, return the most recent non-empty
           candidate (or a trivial valid statement as a last resort).
    """

    MAX_REPAIRS = 2
    REPAIR_TEMPERATURES = (0.0, 0.3)

    BASE_SYSTEM = (
        "You are an expert SQLite programmer. Using only the tables in the "
        "provided schema, write exactly one SQL query that answers the user's "
        "question. Output only the SQL inside a