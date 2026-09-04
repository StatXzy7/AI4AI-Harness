"""Execute-then-repair harness: each generated query is run against the database and execution errors are fed back to the frozen solver for bounded correction."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G7(SQLHarness):
    """Improves a frozen greedy solver with an execute / repair control loop.

    Instead of trusting the first generated statement, the harness executes
    it against the real database. Any hard failure -- a database error, a
    reply with no extractable SQL, or a non-read-only statement -- becomes
    feedback: the next prompt repeats the schema and question, shows the
    failing statement together with the exact database error message, and
    asks the solver to regenerate a corrected query. The loop is bounded by
    ``MAX_ATTEMPTS`` and stops early on the first clean execution or when
    the solver starts repeating an already-failed statement.
    """

    MAX_ATTEMPTS = 4           # 1 initial generation + up to 3 repairs
    MAX_ERROR_CHARS = 600      # clip error text fed back into the prompt
    READ_ONLY_PREFIXES = ("select", "with", "values")

    SYSTEM = (
        "You are a precise SQLite expert. Given a database schema and a "
        "question, reply with exactly one read-only SQLite query inside a "
        "single