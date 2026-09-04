"""Greedy text-to-SQL draft followed by an execution-feedback repair loop that feeds each failed query's database error back to the LLM for corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2BGlmS2G2"]


class P2P2BGlmS2G2(SQLHarness):
    """Text-to-SQL harness with an execution-error repair loop.

    Control flow:
      1. One greedy LLM call turns (schema, question) into a draft query.
      2. The draft is executed against the database with self.execute.
      3. While the current query errors and the repair budget is not spent,
         the failed query *together with its database error message* is added
         to a growing list of failed attempts; that list is rendered into a
         new prompt, the model regenerates a corrected query, and the new
         query is executed in turn (duplicate queries are suppressed so the
         loop cannot ping-pong on the same broken SQL).
      4. The first query that executes successfully is returned; if every
         attempt fails, the most recent attempt is returned.
    """

    MAX_REPAIR_ROUNDS = 3
    MAX_ERROR_CHARS = 800
    # Round 0 repair stays greedy; later rounds escalate temperature so the
    # model can escape a deterministic repetition of the same broken query.
    REPAIR_TEMPERATURES = (0.0, 0.3, 0.7)

    SYSTEM_PROMPT = (
        "You are a precise text-to-SQL translator for SQLite. You always "
        "reply with exactly one SQL query inside a