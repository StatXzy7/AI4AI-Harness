"""Greedy SQL generation wrapped in an execution-feedback repair loop: every candidate statement is executed against the database, and the exact error message (plus the failing SQL) is fed back to the frozen solver for up to three correction rounds, returning the first statement that executes cleanly."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G3(SQLHarness):
    """Text-to-SQL harness with execution-error-guided repair.

    Control flow (a real change vs. a single greedy call):

      1. One greedy generation call produces a candidate SQL statement.
      2. The candidate is validated (must be a read-only SELECT / WITH query)
         and executed against the database.
      3. On failure, the failing statement *and the exact database error* are
         shown back to the frozen solver, which regenerates a corrected query.
      4. Steps 2-3 repeat for at most MAX_REPAIR_ROUNDS rounds.  The first
         statement that executes cleanly is returned immediately; if nothing
         ever executes cleanly, the most recent read-only candidate is
         returned as a best-effort fallback.
    """

    MAX_REPAIR_ROUNDS = 3

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. Reply with exactly one SQL "
        "statement inside a