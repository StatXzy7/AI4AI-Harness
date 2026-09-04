"""Repair harness: greedy SQL generation that is validated by real execution, with SQLite error messages fed back into bounded corrective regeneration rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G5(SQLHarness):
    """Text-to-SQL harness that self-repairs its SQL with execution feedback.

    Control flow (a genuine loop, not just a longer prompt):

        generate(sql_0) -> execute(sql_0) --ok--> return sql_0
                               |
                             error
                               v
        build a repair prompt containing the failing SQL *and* the exact
        database error text -> regenerate sql_1 -> execute(sql_1) -> ...

    The loop stops when a query executes cleanly, when the repair budget
    (MAX_REPAIRS extra generations) is exhausted, or when the model starts
    repeating an already-failed query. The underlying solver stays frozen
    (temperature 0.0, n=1 on every call); only the orchestration changes.
    """

    #: corrective generations allowed after the initial greedy one
    MAX_REPAIRS = 3

    _SYSTEM = (
        "You are a precise text-to-SQL engine targeting SQLite. "
        "Given a database schema and a question, output exactly one SQL "
        "query inside a