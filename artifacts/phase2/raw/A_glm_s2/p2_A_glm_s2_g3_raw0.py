"""Execution-guided repair loop: the harness greedily generates one SQL query, executes it, and feeds the failed query plus its exact database error back to the frozen solver for up to three regeneration rounds until a query executes."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G3(SQLHarness):
    """Greedy Text-to-SQL generation plus an execution-error-driven repair loop.

    Control flow per question:

    1. Ask the frozen solver (temperature 0) for one SQL query.
    2. Extract the SQL and run it against the database via ``self.execute``.
    3. If it executes, return it immediately.
    4. Otherwise build a new prompt that shows the schema, the question, the
       failing SQL and the exact database error, let the solver regenerate
       the query, and re-execute the result.
    5. Repeat for at most ``MAX_ATTEMPTS`` generations, stopping early if the
       solver repeats a query that was already run; if nothing ever executes,
       return the newest guard-passing query (the solver's most informed
       attempt), or a trivially valid query as a last resort.
    """

    MAX_ATTEMPTS = 4                 # 1 initial generation + 3 repair rounds
    MAX_SQL_CHARS = 4000             # sanity cap on the extracted SQL
    MAX_ERROR_CHARS = 600            # cap on error text fed back to the solver

    _BLOCKED_HEADS = frozenset({
        "alter", "attach", "create", "delete", "detach", "drop", "explain",
        "grant", "insert", "pragma", "replace", "revoke", "truncate",
        "update", "vacuum",
    })

    SYSTEM_PROMPT = (
        "You are a precise SQLite expert. You reply with exactly one "
        "read-only SQL query inside a