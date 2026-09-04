"""Execution-guided repair loop: generate one greedy SQL candidate, execute it against the database, and feed the exact error message back into up to three corrective regeneration calls until a query executes cleanly."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G5(SQLHarness):
    """Greedy SQL generation wrapped in an execution-error repair loop.

    Control flow (a real change vs. a single greedy call):

      1. One greedy LLM call produces a candidate SQL statement.
      2. The candidate is executed against the real database.
      3. If execution fails, the failing SQL *and the exact database error*
         are fed back into a repair prompt; the frozen solver regenerates.
      4. Steps 2-3 repeat up to ``MAX_REPAIRS`` times (earlier failures are
         also listed so the model does not repeat them).
      5. The first query that executes cleanly is returned; if every attempt
         fails, the most recent non-empty candidate is returned.
    """

    MAX_REPAIRS = 3

    SYSTEM_INITIAL = (
        "You are an expert SQLite programmer. Using only the tables and "
        "columns in the provided schema, translate the question into a "
        "single valid SQLite SELECT query. Reply with exactly one SQL "
        "statement inside a