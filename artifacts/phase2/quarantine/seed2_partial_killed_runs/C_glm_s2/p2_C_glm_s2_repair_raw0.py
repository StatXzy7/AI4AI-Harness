"""This harness generates SQL with the frozen GLM solver, executes it against SQLite, and, whenever execution fails, feeds the exact SQLite error message back to the solver to regenerate the query up to 2 times."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS2Repair(SQLHarness):
    """Generate -> execute -> repair loop driven by the exact SQLite error.

    Control flow (the strategy lives here, not just in the prompts):

        1. GENERATE : one call to the frozen solver from (schema, question).
        2. EXECUTE  : run the candidate via self.execute().
        3. REPAIR   : if execution failed, re-generate with the failed SQL and
                      the verbatim SQLite error included in the prompt, then
                      go back to step 2 -- at most MAX_REPAIRS (= 2) times.

    The last generated SQL is returned as the best-effort answer even if the
    repair budget is exhausted without a successful execution.
    """

    MAX_REPAIRS = 2    # error-feedback regeneration rounds after attempt #1
    TEMPERATURE = 0.0  # frozen solver: deterministic decoding on every attempt

    SYSTEM = (
        "You are an expert SQLite programmer. Given a database schema and a "
        "natural-language question, you write exactly one SQLite query that "
        "answers the question. Use only tables and columns that appear in the "
        "schema. Reply with a single SQL statement inside a