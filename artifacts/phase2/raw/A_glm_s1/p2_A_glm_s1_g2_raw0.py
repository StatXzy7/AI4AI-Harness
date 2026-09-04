"""Repair harness: greedily draft SQL, execute it against the live database, and regenerate up to three times with the execution error fed back until a query runs cleanly."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G2(SQLHarness):
    """Draft-then-repair control flow around the frozen solver.

    A greedy draft query is executed on the real database; whenever execution
    fails, the offending SQL together with the database's error message is fed
    back into the prompt and the solver regenerates a corrected query. A small
    budget of repair rounds is allowed, identical re-proposed failing queries
    are not wastefully re-executed, and the first query that executes cleanly
    is returned immediately.
    """

    MAX_ATTEMPTS = 4  # one initial greedy draft + up to three error-driven repairs

    SYSTEM = (
        "You are an expert Text-to-SQL engine. Given a database schema and a "
        "natural-language question, write exactly one SQLite query that answers "
        "the question. Reply with only the SQL, in a single