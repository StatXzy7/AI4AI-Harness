"""An execution-repair loop that executes every generated SQL query and feeds any resulting database error message back to the LLM for corrective regeneration (up to three attempts)."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2AGlmS1G0"]


class P2P2AGlmS1G0(SQLHarness):
    """Greedy Text-to-SQL generation wrapped in an execution-error repair loop.

    Control flow per question:
      1. Ask the frozen LLM for one SQL query (temperature 0).
      2. Execute the extracted query with ``self.execute``.
      3. If execution succeeds, return it immediately.
      4. If execution fails (or no SQL could be extracted), append the failing
         SQL plus its exact error message to a growing failure history and
         re-prompt the LLM for a corrected query.
      5. Repeat for at most ``max_attempts`` rounds; never re-execute a query
         that already failed verbatim.

    If nothing executes cleanly, the most recent (most informed) candidate is
    returned so downstream grading still receives a SQL string.
    """

    max_attempts = 3  # 1 initial generation + up to 2 repair generations

    system_prompt = (
        "You are an expert SQL engineer. Using only the tables and columns "
        "defined in the supplied schema, write exactly one SQL query that "
        "answers the user's question. Respond with a single SQL statement "
        "inside a