"""Self-correcting Text-to-SQL harness that generates a query, executes it, and—when execution fails—feeds the exact SQLite error back to the model to regenerate a fixed query for up to two repair rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS1Repair(SQLHarness):
    """Generate -> execute -> repair-loop harness.

    Control flow (the strategy is realized here, not just in the prompt):

      1. Ask the LLM for one SQLite query given the schema and question.
      2. Execute the extracted SQL via ``self.execute()``.
      3. If execution fails, show the model its own failing SQL together
         with the *exact* SQLite error message and ask it to regenerate a
         corrected query.
      4. Repeat step 3 at most ``MAX_REPAIRS`` (= 2) times, re-executing
         each regenerated candidate. Return the first query that executes
         successfully; if the repair budget is exhausted, return the last
         generated query as the best-effort answer.
    """

    MAX_REPAIRS: int = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. Using only the provided database "
        "schema, write exactly one SQLite query that answers the user's question. "
        "Output the query in a single