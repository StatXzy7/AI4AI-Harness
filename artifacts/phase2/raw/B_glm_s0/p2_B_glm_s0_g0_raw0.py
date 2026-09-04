"""Execution-guided self-repair: the harness executes every generated SQL query against the database and, when execution fails, replays the failing query plus the engine's error message back to the frozen solver for up to three corrective regeneration rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G0(SQLHarness):
    """Greedy text-to-SQL generation wrapped in an execution-driven repair loop.

    Control flow of :meth:`solve`:

    1. Prompt the frozen solver once (greedy, temperature 0) for a SQL query.
    2. Execute the extracted query with ``self.execute``.
    3. If the database reports an error, build a repair prompt containing the
       failed query and the exact error text, and ask the solver to regenerate
       a corrected query.  Repeat for up to ``MAX_ATTEMPTS`` total generations.
    4. Return the first query that executes cleanly; if every attempt fails,
       return the most recent non-empty query the solver produced.
    """

    MAX_ATTEMPTS = 3
    _MAX_ERR_CHARS = 400

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL translator. Given a database schema and "
        "a question, answer with exactly one SQL query inside a