"""Execution-guided repair loop: greedily generate a SQL query, execute it, and feed each execution error back to the LLM for up to three correction rounds until a query runs cleanly."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G2(SQLHarness):
    """A repair loop wrapped around the frozen greedy solver.

    Control flow (a real change vs. a single greedy call):

        generate -> execute -> on failure append (query, error) to a failure
        history -> regenerate with that history -> execute -> ...

    The first query that executes cleanly is returned immediately. If every
    round fails, the most recent (best-informed) candidate is returned as a
    last resort, so the method always yields a non-empty SQL string.
    """

    MAX_ATTEMPTS = 4        # 1 initial generation + up to 3 repair rounds
    MAX_ERROR_CHARS = 600   # cap on error text echoed back into the prompt
    FALLBACK_SQL = "SELECT 1"

    SYSTEM_PROMPT = (
        "You are an expert SQLite engineer. Given a database schema and a "
        "natural-language question, write exactly one SQLite SELECT query that "
        "answers the question. Use only tables and columns that appear in the "
        "schema. Reply with the query in a