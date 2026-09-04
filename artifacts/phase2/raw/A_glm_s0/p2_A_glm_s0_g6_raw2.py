"""Execution-feedback repair loop: the greedy SQL generation is executed against the database and, whenever execution fails, the failed query together with its error message is fed back to the frozen solver for up to three corrective regenerations."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS0G6(SQLHarness):
    """Greedy frozen solver wrapped in an execution-guided repair loop.

    Control flow per question:
      1. Build a prompt (schema + question + history of failed attempts).
      2. One greedy LLM call -> candidate SQL (via bridge.extract_sql).
      3. Execute the candidate with self.execute.
      4. If it executes cleanly -> return it immediately.
      5. Otherwise, append (bad_sql, executor_error) to the failure history
         and go to 1, so the next generation actually sees the database
         error it must fix.
    After MAX_ROUNDS attempts the most recent candidate is returned as a
    best-effort answer.
    """

    MAX_ROUNDS = 4          # 1 initial generation + up to 3 error-driven repairs
    MAX_ERROR_CHARS = 400   # cap on error text echoed back into the prompt
    READONLY_STARTS = ("select", "with", "values")

    SYSTEM_PROMPT = (
        "You are a precise Text-to-SQL translator. Using only the tables and "
        "columns that appear in the given schema, write exactly one SQLite "
        "query that answers the question. Answer with a single