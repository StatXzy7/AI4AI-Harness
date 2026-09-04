"""Execute the generated SQL and feed the engine's error messages back to the frozen solver for bounded corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G6(SQLHarness):
    """Greedy generation verified by execution, with error-driven repair rounds.

    Control flow:
      1. Ask the frozen LLM for one SQLite query (greedy, temperature 0).
      2. Run it against the database with self.execute().
      3. If execution fails, append the exact engine error (and the failed
         query) to the prompt and regenerate, up to max_attempts total calls.
      4. Return the first query that executes cleanly; if none does, return
         the most recent (best-informed) attempt.
    """

    #: total generation attempts = 1 initial + (max_attempts - 1) repairs
    max_attempts = 3

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite analyst. Given a database schema and a "
            "natural-language question, output exactly one SQLite query that "
            "answers the question. Output only the query, inside a