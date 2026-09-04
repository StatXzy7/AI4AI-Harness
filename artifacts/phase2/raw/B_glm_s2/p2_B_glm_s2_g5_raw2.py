"""Greedy text-to-SQL generation wrapped in an execution-repair loop that feeds database error messages back to the solver for up to three corrective regenerations."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G5(SQLHarness):
    """Weak-solver harness with an execution-error repair loop.

    ``solve`` is not a single generation call.  It runs a bounded
    generate -> execute -> critique loop:

    1. Ask the frozen solver for one SQL query (temperature 0).
    2. Execute that query against the target database.
    3. On failure -- a database error, an output with no extractable SQL,
       or an exact repeat of an already-failed query -- record the
       offending SQL together with the error message.
    4. Re-prompt the solver with the schema, the question, and the
       accumulated (SQL, error) pairs, asking for a corrected query.
    5. Return the first query that executes cleanly; if every attempt
       fails, return the last non-empty candidate as a best effort.

    The loop is capped at ``MAX_ATTEMPTS`` solver calls, so worst case a
    question costs 4 generations instead of 1, while questions the weak
    solver already answers correctly still cost exactly one call plus one
    (successful) execution.
    """

    MAX_ATTEMPTS = 4            # 1 greedy generation + up to 3 repair rounds
    MAX_HISTORY_IN_PROMPT = 4   # failed (SQL, error) pairs echoed to the model

    SYSTEM = (
        "You are an expert text-to-SQL translator. Given a database schema "
        "and a natural-language question, output exactly one SQL query that "
        "answers the question. Output only the SQL inside a