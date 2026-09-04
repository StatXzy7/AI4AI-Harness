"""Repair-loop text-to-SQL harness: a greedy SQL candidate is executed against the database and every execution error is fed back into the LLM prompt for up to three corrective regenerations."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G5(SQLHarness):
    """Greedy generation + execution-error repair loop.

    Control flow (a real change vs. a single greedy call):

      1. One greedy LLM call produces an initial SQL candidate.
      2. The candidate is screened (read-only, single statement) and then
         executed on the live database.
      3. If execution fails, the exact DB error message -- together with the
         offending SQL, the schema, and the recent failure history -- is fed
         back into a corrective prompt, and the LLM regenerates the query.
      4. Steps 2-3 repeat for at most ``MAX_ROUNDS`` rounds; the first
         candidate that executes cleanly is returned, otherwise the last one.
    """

    SYSTEM = "You are a precise text-to-SQL engine. Respond with SQL only."

    #: total attempts = 1 initial greedy generation + 3 error-driven repairs
    MAX_ROUNDS = 4

    _READONLY_HEADS = ("select", "with")

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        schema = (getattr(self, "schema", "") or "").strip()
        question = (question or "").strip()

        tried = {}     # sql -> error message of its failed attempt
        attempts = []  # ordered [(sql, error)] used to build the repair prompt

        sql = self._initial_sql(question, schema)

        for round_idx in range(self.MAX_ROUNDS):
            if sql in tried:
                # Degenerate repair: the LLM repeated a query that already
                # failed; don't waste an execution on it, complain instead.
                issue = ("This query is identical to an earlier failed attempt "
                         "(error: %s). Produce a materially different query."
                         % tried[sql])
            else:
                issue = self._static_check(sql)
                if issue is None:
                    result = self._safe_execute(sql)
                    if result.get("ok"):
                        return sql  # first query that runs cleanly wins
                    issue = self._failure_message(result)
                tried[sql] = issue

            attempts.append((sql, issue))

            if round_idx + 1 >= self.MAX_ROUNDS:
                break  # repair budget exhausted
            sql = self._repair_sql(question, schema, attempts)

        # Nothing ever executed cleanly; hand back the most recent candidate.
        return sql

    # ------------------------------------------------------------------ #
    # LLM interaction
    # ------------------------------------------------------------------ #

    def _initial_sql(self, question: str, schema: str) -> str:
        prompt = (
            "You are given a database schema and a natural-language question.\n"
            "Write one SQLite query that answers the question.\n"
            "\n"
            "Schema:\n{schema}\n"
            "\n"
            "Question: {question}\n"
            "\n"
            "Requirements:\n"
            "- Exactly one read-only statement that starts with SELECT or WITH.\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- Qualify columns with their table name and prefer explicit JOINs.\n"
            "- Output only the SQL inside one