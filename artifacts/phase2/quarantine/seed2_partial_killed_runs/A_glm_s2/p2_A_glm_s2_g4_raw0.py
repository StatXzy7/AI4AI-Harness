"""Repair loop: greedily generate one SQL query, execute it against the database, and feed the exact execution error (plus the failing SQL) back to the LLM for bounded corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G4(SQLHarness):
    """Greedy text-to-SQL generation wrapped in an execution-driven repair loop.

    Control flow per question:
      1. Ask the LLM (temperature 0.0) for one SQLite query given the schema.
      2. Execute the extracted query via ``self.execute``.
      3. If execution fails, append the failing SQL and its verbatim error
         message to the prompt and ask the LLM to fix it.
      4. Repeat up to ``MAX_ATTEMPTS`` rounds; return the first query that
         executes cleanly, otherwise the best fallback candidate.
    """

    MAX_ATTEMPTS = 4

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL agent. Given a database schema and a "
        "natural-language question, write exactly one SQLite query that answers "
        "the question. Output only the query inside a single