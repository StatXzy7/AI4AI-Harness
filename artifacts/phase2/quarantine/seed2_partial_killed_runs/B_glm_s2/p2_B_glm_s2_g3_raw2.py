"""Repair-loop harness: generate SQL greedily, execute it, and feed execution errors back to the frozen solver for bounded corrective regeneration."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G3(SQLHarness):
    """Greedy generation plus execution-guided corrective rounds.

    The frozen solver is asked once for a SQL answer to the question. The
    candidate is then executed against the live database; if execution
    reports an error, the offending query and its error message are appended
    to a failure log that is replayed to the solver (together with the schema
    and the question) so it can emit a corrected query. The loop is bounded
    by ``MAX_REPAIRS`` extra rounds and stops early on the first query that
    executes cleanly, when the solver repeats an already-failed query, or
    when no SQL can be extracted from a reply.
    """

    MAX_REPAIRS = 3  # extra corrective rounds after the initial generation
    _READ_ONLY = ("select", "with", "values")

    SYSTEM = (
        "You are an expert SQLite text-to-SQL engineer. Reply with exactly "
        "one read-only SQL SELECT statement, placed in a single