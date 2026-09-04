"""Greedy text-to-SQL generation wrapped in an execution-repair loop that feeds database engine error messages back to the solver to regenerate corrected queries."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G0(SQLHarness):
    """Frozen weak solver improved with execution-error-driven repair.

    Control flow (a real change versus a single greedy call):

      1. One greedy LLM call maps (schema, question) -> candidate SQL.
      2. The candidate is executed against the database.
      3. If and only if execution raises an engine error, the exact error
         message -- together with every earlier failed attempt -- is fed
         back into a repair prompt, and the solver regenerates the query.
      4. Steps 2-3 repeat up to ``MAX_REPAIRS`` times.
      5. The first query that executes cleanly wins. An empty-but-valid
         result set is NOT treated as failure (a correct query may
         legitimately return zero rows). If every attempt fails, the most
         recent non-empty attempt (the one made with the most error
         context) is returned.
    """

    #: How many repair rounds (extra LLM calls) are allowed per question.
    MAX_REPAIRS = 3

    _SYSTEM = (
        "You are an expert text-to-SQL translator. Answer with exactly one "
        "SQLite query inside a