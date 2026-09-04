"""Generate SQL with the frozen solver, execute it, and on failure feed the exact SQLite error back to regenerate, up to 2 repair rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS1Repair(SQLHarness):
    """Weak-solver wrapper implementing a generate -> execute -> repair loop.

    Control flow (the strategy lives here, not only in the prompt):

      1. Ask the frozen LLM solver for a SQL query given the schema + question.
      2. Extract the SQL and execute it via ``self.execute()``.
      3. If execution fails, build a repair prompt containing the failed SQL
         and the *exact* SQLite error string, and ask the solver to regenerate.
      4. Repeat the repair round up to ``MAX_REPAIRS`` (2) times.
      5. Return the first SQL that executes cleanly; otherwise return the last
         attempt as a best effort.
    """

    MAX_REPAIRS = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. Given a database schema and a "
        "natural-language question, write a single valid SQLite query that "
        "answers the question. Use only tables and columns that appear in the "
        "schema. Respond with exactly one SQL statement inside a