"""Execution-feedback repair harness: generate a SQL candidate, execute it against the SQLite database, and on failure feed the exact SQLite error message back to the frozen solver to regenerate the query up to two times."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS1Repair(SQLHarness):
    """Weak-solver wrapper that repairs SQL using execution feedback.

    Control flow (the strategy is realized here, not just in the prompt):
      1. Ask the frozen solver for one SQLite query (schema + question).
      2. Execute the extracted query via self.execute().
      3. If execution fails, show the solver the failed query together with
         the exact SQLite error string and ask it to regenerate.
      4. Repeat step 3 at most MAX_REPAIRS times.
      5. Return the first query that executes successfully, otherwise the
         last generated query.
    """

    MAX_REPAIRS: int = 2  # initial generation + up to 2 repair regenerations

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. Given a database schema and a "
        "natural-language question, write exactly one SQLite query that answers "
        "the question. Output the query inside a single