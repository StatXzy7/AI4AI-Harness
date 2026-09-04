"""Greedy SQL generation wrapped in an execution-repair loop: each candidate query is executed against the database and any error message is fed back to the LLM for corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G3(SQLHarness):
    """Execution-guided repair loop around a frozen greedy SQL generator.

    Control flow (a real change versus a single greedy call):

      1. One greedy LLM call turns (schema, question) into a candidate query.
      2. The candidate is executed against the database via ``self.execute``.
      3. If execution fails, the exact engine error message plus the offending
         query are packed into a repair prompt, and the LLM regenerates the
         query in a second (and possibly third) call.
      4. Steps 2-3 repeat up to ``MAX_REPAIR_ROUNDS`` times; the loop stops
         early when the model repeats a byte-identical failing query. The
         first query that executes cleanly wins, otherwise the most recent
         non-empty candidate is returned as a best effort.
    """

    MAX_REPAIR_ROUNDS = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite analyst. Given a database schema and a "
        "natural-language question, output exactly one SQL query that answers "
        "the question. Respond with a single SQL query inside a