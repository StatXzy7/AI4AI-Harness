"""Repair-loop harness: generate one SQL query greedily, execute it against the database, and feed each verbatim execution error back to the frozen solver for up to three corrective regenerations before returning the first query that executes cleanly."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G4(SQLHarness):
    """Greedy generation hardened by an execution-error repair loop.

    Control flow (a real change over a single call, not just a longer prompt):

      1. One greedy LLM call produces a candidate query (temperature 0).
      2. The candidate is executed with ``self.execute``.
      3. If the database reports an error, a repair prompt is built that
         contains the schema, the question, the failing query and the
         *verbatim* database error, and the solver regenerates.
      4. Duplicate failing queries are suppressed; later repair rounds use a
         higher temperature so the loop cannot get stuck re-emitting the
         identical broken query.
      5. The first query that executes cleanly is returned immediately; if
         every attempt fails, the last non-empty candidate is returned.
    """

    MAX_ATTEMPTS = 4                        # 1 greedy call + up to 3 repairs
    TEMPERATURES = (0.0, 0.0, 0.3, 0.6)     # per-attempt temperature schedule
    MAX_HISTORY = 3                         # failed attempts echoed back
    MAX_ERROR_CHARS = 400                   # cap on error text fed to the LLM
    FALLBACK_SQL = "SELECT 1;"              # only if no SQL was ever extracted

    SYSTEM = (
        "You are a precise text-to-SQL engine. Given a database schema and a "
        "question, you output exactly one SQL query inside a