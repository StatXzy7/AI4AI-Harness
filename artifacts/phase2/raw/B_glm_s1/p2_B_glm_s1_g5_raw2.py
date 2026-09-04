"""Repair-loop text-to-SQL harness: a greedy SQL proposal is executed, and any execution error (together with the failing SQL) is fed back to the LLM for up to three corrective regenerations."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G5(SQLHarness):
    """Greedy proposal followed by execution-error-driven repair rounds.

    Control flow (a real change vs. a single greedy call):

        propose -> execute -> (on error) propose-with-feedback -> execute -> ...

    * The first proposal is a single deterministic (temperature 0) call.
    * Every proposal is actually executed against the database.
    * If execution fails, the next LLM call receives the schema, the
      question, the failed SQL and the verbatim database error, and is
      asked for a corrected query.
    * The loop stops when a proposal executes cleanly, after MAX_REPAIRS
      repair rounds, or when a proposal repeats an earlier one (a
      deterministic model would otherwise cycle forever).
    """

    MAX_REPAIRS = 3          # extra LLM calls allowed after the first failure
    MAX_ERROR_CHARS = 500    # keep the fed-back error message bounded

    _SYSTEM_FIRST = (
        "You are an expert text-to-SQL translator. Given a database schema "
        "and a natural-language question, output exactly one SQLite SELECT "
        "query that answers the question. Output only the SQL, wrapped in a "
        "