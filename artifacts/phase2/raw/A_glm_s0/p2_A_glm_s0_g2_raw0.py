"""Greedy SQL generation followed by an execution-verified repair loop that feeds database error messages back to the model for corrective regeneration."""

# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS0G2(SQLHarness):
    """Text-to-SQL harness that verifies each candidate query against the real
    database and repairs it when execution fails.

    Control flow (a genuine change vs. a single greedy call):

      1. Ask the model for one SQL query (greedy, temperature 0).
      2. Execute the extracted query via ``self.execute``.
      3. If it executes cleanly, return it immediately.
      4. If execution fails, re-prompt the model with the *failed query*, the
         *exact database error*, the schema, and the question, asking for a
         corrected query; go back to step 2.
      5. After ``MAX_REPAIR_ROUNDS`` rounds without success, return the most
         recent corrected attempt (the one generated with the most error
         context), or "" if the model never produced extractable SQL.
    """

    MAX_REPAIR_ROUNDS = 3   # 1 initial generation + 2 error-driven repairs
    MAX_ERROR_CHARS = 400   # cap on executor error text fed back to the model

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "natural-language question, output exactly one SQLite query that answers "
        "the question. Use only tables and columns that appear in the schema. "
        "Reply with the query alone, wrapped in a