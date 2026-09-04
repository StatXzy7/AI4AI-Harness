"""Repair loop: greedily generate SQL, execute it against the database, and feed execution errors (or empty result sets) back to the frozen model for corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2AGlmS1G2"]


class P2P2AGlmS1G2(SQLHarness):
    """Text-to-SQL harness with an execution-guided repair loop.

    Control flow (a real change vs. a single greedy call):

        1. One greedy LLM call turns (schema, question) into a candidate query.
        2. The candidate is executed against the real database.
        3. If the database rejects the query, the exact engine error message
           plus the offending SQL are sent back to the model, which is asked
           for a corrected query.  A query that runs but returns zero rows is
           also given a chance to be "de-over-constrained".
        4. This repeats for at most MAX_ATTEMPTS generations.  The best query
           ever seen is returned (executed-with-rows > executed-empty >
           never-executed), so a bad repair can never destroy a working query.
    """

    MAX_ATTEMPTS = 3         # initial generation + up to 2 repairs
    REPAIR_ON_EMPTY = True   # also repair "ran fine but returned 0 rows"
    SYSTEM = (
        "You are an expert SQLite programmer. You answer natural-language "
        "questions about a database by writing exactly one read-only SQL "
        "SELECT query."
    )

    # ------------------------------------------------------------------ #
    # entry point                                                        #
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        schema = self.schema
        sql = self._initial(question, schema)

        best_sql = None
        best_rank = -1  # 2 = executed + returned rows, 1 = executed + 0 rows
        last_sql = ""   # last query we actually dared to execute

        for attempt in range(self.MAX_ATTEMPTS):
            feedback = None

            if not sql:
                feedback = (
                    "No SQL query could be extracted from your reply. Reply "
                    "with the query inside a