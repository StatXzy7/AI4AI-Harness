"""Execute-and-repair control flow: each generated query is run against the database and, when execution fails, the database error is fed back into the prompt so the frozen solver can regenerate a corrected query, for up to a bounded number of rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G0(SQLHarness):
    """A frozen weak text-to-SQL solver wrapped in an execute-then-repair loop.

    Control flow per question:

    1. Ask the solver for one query (greedy / deterministic).
    2. Execute that query on the target database.
    3. Success -> return it immediately.  The happy path costs exactly one
       LLM call plus one execution, i.e. zero overhead over plain generation.
    4. Failure -> record ``(sql, error)`` in a feedback history and ask the
       solver for a corrected query, up to ``MAX_ATTEMPTS`` total calls.
    5. A query that repeats an already-failed statement verbatim is rejected
       before execution, so the attempt budget is never spent re-running a
       statement whose fate is already known.
    6. If every attempt fails, the most recent syntactic candidate is returned
       so downstream scoring still receives a SQL string.
    """

    MAX_ATTEMPTS = 4        # total LLM calls: 1 greedy generation + up to 3 repairs
    MAX_ERROR_CHARS = 400   # cap on how much of the executor error is echoed back

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL translator working against a SQLite "
        "database. Write exactly one SQL SELECT query that answers the user's "
        "question using only the tables and columns that appear in the schema. "
        "Put the query inside a single