"""Repair-loop harness: every generated SQL query is executed against the live database and, when execution fails, the exact error text is replayed to the frozen solver for up to three rounds of correction."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G0(SQLHarness):
    """Execute-then-repair control loop wrapped around a frozen Text-to-SQL solver.

    Flow for every question:
      1. Ask the solver for one SQL query (greedy decode).
      2. Execute that query on the real database.
      3. If it executes -- even with zero result rows -- return it immediately.
      4. If it errors, build a repair prompt containing the schema, the question,
         every failed query so far, and each verbatim database error message, then
         ask the solver for a corrected query.
      5. Repeat until a query executes or the repair budget (3 fixes) is spent;
         then return the most recent non-empty candidate as a best effort.

    Candidate selection is driven purely by execution feedback, so the extra LLM
    calls are genuine repairs rather than sampling/voting.
    """

    MAX_ATTEMPTS = 4          # 1 initial generation + 3 repair generations
    REPAIR_TEMPERATURE = 0.3  # mild diversification so a repair can escape the same broken query
    MAX_ERROR_CHARS = 600     # truncate huge driver error messages before replaying them

    SYSTEM = (
        "You are an expert SQL writer. Reply with exactly one SQL SELECT "
        "statement, optionally wrapped in a