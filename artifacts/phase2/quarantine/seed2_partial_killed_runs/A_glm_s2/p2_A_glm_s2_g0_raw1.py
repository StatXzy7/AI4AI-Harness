"""A greedy first SQL draft is executed, and any SQLite error or empty result set is fed back to the LLM for up to two corrective regeneration rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G0(SQLHarness):
    """Text-to-SQL harness that improves on a single greedy call with an
    execution-feedback repair loop.

    Control flow of ``solve``:

      1. One greedy LLM call turns (schema, question) into a candidate query,
         extracted with ``bridge.extract_sql``.
      2. The candidate is executed against the database via ``self.execute``.
      3. While the latest query raised an error or returned zero rows -- and at
         most ``MAX_REPAIR_ROUNDS`` times -- a repair prompt containing the
         previous SQL plus the *concrete* execution feedback (verbatim SQLite
         error text, or "executed but returned 0 rows") is sent back to the LLM.
         The regenerated query is executed in turn.
      4. The harness returns the best candidate observed: the first query that
         executed and returned rows, else the first query that merely executed,
         else the most recent attempt (so a string is always returned).
    """

    MAX_REPAIR_ROUNDS = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite analyst. You answer with exactly one "
        "SQLite SELECT query and nothing else."
    )

    def solve(self, question: str) -> str:
        sql, result = self._initial_generation(question)
        candidates = [(sql, result)]

        for _ in range(self.MAX_REPAIR_ROUNDS):
            if self._returns_rows(result):
                break  # executed fine and produced rows: nothing to repair
            new_sql, new_result = self._repair_generation(question, sql, result)
            if not new_sql or new_sql == sql:
                break  # model made no progress; do not retry identically
            sql, result = new_sql, new_result
            candidates.append((sql, result))

        return self._best_candidate(candidates)

    # ------------------------------------------------------------------ #
    # Control-flow steps
    # ------------------------------------------------------------------ #

    def _initial_generation(self, question):
        """Stage 1: greedy draft SQL from schema + question, then execute it."""
        prompt = (
            "Using the database schema below, write one SQLite query that "
            "answers the question.\n\n"
            "Schema:\n"
            "{schema}\n\n"
            "Question: {question}\n\n"
            "Output only the SQL query, wrapped in a