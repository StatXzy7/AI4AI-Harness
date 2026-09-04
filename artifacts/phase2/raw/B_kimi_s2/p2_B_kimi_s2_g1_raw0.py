"""A repair-loop harness: generate SQL greedily, execute it, and feed any execution error back to the frozen LLM for iterative regeneration until the query runs or the attempt budget is exhausted."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G1(SQLHarness):
    """Repair harness: initial greedy SQL generation, then an execution-error
    feedback loop. Each failed execution appends (sql, error) to a failure
    history that is shown to the LLM so it can produce a corrected query.
    """

    MAX_ATTEMPTS = 4  # total generations: 1 initial + up to 3 repairs

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL engine. Given a database schema and "
            "a natural-language question, produce exactly one syntactically "
            "valid SQL query that answers it. Output only the SQL, wrapped in "
            "a