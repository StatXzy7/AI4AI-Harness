"""Generate a candidate SQLite query, execute it, and on failure feed the exact SQLite error back to the model and regenerate up to two times."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS1Repair"]


class P2P2CGlmS1Repair(SQLHarness):
    """Weak-solver wrapper with an execute-then-repair control loop.

    The strategy is realized in the control flow, not just the prompt:
      1. Ask the frozen LLM for one SQL query given schema + question.
      2. Execute the extracted query via ``self.execute``.
      3. If execution fails, show the model its own failing query together
         with the *exact* SQLite error string and ask for a corrected query.
      4. Repeat step 3 at most ``MAX_REPAIRS`` (= 2) times, i.e. at most
         3 generation attempts and 3 executions in total.
      5. Return the first query that executes cleanly; if none does,
         return the last candidate generated.
    """

    MAX_REPAIRS = 2  # regeneration attempts after the initial generation

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. Given a database schema and a "
        "natural-language question, you write exactly ONE SQLite SQL query "
        "that answers the question. Use only tables and columns that appear "
        "in the schema. Reply with a single