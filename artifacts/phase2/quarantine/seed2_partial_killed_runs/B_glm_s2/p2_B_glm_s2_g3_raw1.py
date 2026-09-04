"""Repair-loop harness: greedily generate a candidate SQL query, execute it against the target database, and feed the concrete execution error (or a zero-rows diagnosis) back to the solver for up to two corrective regenerations before falling back to the best query observed."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2BGlmS2G3"]


class P2P2BGlmS2G3(SQLHarness):
    """Text-to-SQL harness with an execution-feedback repair loop.

    Control flow per question:

    1. Generate one SQL query greedily from (schema, question).
    2. Execute the extracted query on the real database.
    3. If execution raises a database error -- or the query succeeds but
       returns zero rows, which for a weak solver usually means a wrong
       table, join, or filter -- build a repair prompt that shows the
       offending SQL together with the exact database error message (or
       the zero-rows diagnosis) and regenerate.
    4. Repeat for at most ``MAX_ATTEMPTS`` generations.

    Return policy: the first query that executes and returns rows wins;
    otherwise the first query that at least executed without error is
    returned as a fallback; otherwise the last generated SQL is returned.
    The loop also stops early if the solver repeats the exact same SQL,
    since identical attempts cannot make further progress.
    """

    MAX_ATTEMPTS = 3

    SYSTEM = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "natural-language question, output exactly one SQLite query. Put the "
        "query in a single