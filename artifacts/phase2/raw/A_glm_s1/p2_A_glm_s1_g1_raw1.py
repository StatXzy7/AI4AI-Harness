"""Self-repair loop: every generated SQL is executed against the database and, on failure, the broken query plus its exact DB error message are fed back to the frozen solver for a corrective regeneration round (up to two repairs)."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G1(SQLHarness):
    """Greedy generation + execute-verify-repair control loop.

    Control flow:
      1. Ask the frozen solver (greedy, temperature 0.0) for one read-only
         SELECT query against the given schema.
      2. Execute the query on the real database via self.execute().
      3. If execution fails, record the failing SQL and the database error,
         then re-prompt the solver with that history so it can fix the query
         (up to MAX_ROUNDS total attempts). A deterministic trailing-
         semicolon retry is attempted before declaring an attempt failed.
      4. Return the first query that executes cleanly; otherwise return the
         last read-only candidate as a best effort (never a rejected,
         non-read-only statement).
    """

    MAX_ROUNDS = 3          # 1 initial generation + up to 2 repair rounds
    MAX_ERROR_CHARS = 400   # cap on error text fed back into the prompt

    SYSTEM = (
        "You are an expert SQLite analyst. Given a database schema and a "
        "natural-language question, write exactly one read-only SQLite query "
        "that answers the question. Output only the SQL inside a single "
        "