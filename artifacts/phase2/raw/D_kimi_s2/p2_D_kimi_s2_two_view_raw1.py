"""Harness that drafts the query from two independent formulations (join-based and subquery-based), executes both, and returns the first SQL whose result is non-empty."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2TwoView(SQLHarness):
    """Two-view Text-to-SQL harness.

    The frozen weak solver is queried twice with structurally independent
    instructions: once constrained to a JOIN-based formulation and once
    constrained to a subquery-based formulation. Both candidate SQL strings
    are executed against the database; the first candidate that succeeds and
    yields at least one row is returned. If neither yields rows, the first
    candidate that at least executes without error is returned, and if both
    fail outright the join-based draft is returned as a best-effort fallback.
    """

    _JOIN_INSTRUCTION = (
        "Formulate the answer as a single SQL query that expresses all "
        "inter-table relationships through explicit JOIN clauses. Do not use "
        "subqueries, CTEs, or nested SELECT statements; put every filter and "
        "aggregation in the outer query over the joined tables."
    )

    _SUBQUERY_INSTRUCTION = (
        "Formulate the answer as a single SQL query that avoids JOIN clauses "
        "and instead expresses inter-table relationships through nested "
        "subqueries (IN, EXISTS, or scalar subqueries). Keep the outer query "
        "on a single table wherever possible."
    )

    def solve(self, question: str) -> str:
        # Draft 1: join-based formulation (independent prompt/view).
        join_sql = self._draft(question, self._JOIN_INSTRUCTION)
        # Draft 2: subquery-based formulation (independent prompt/view).
        subquery_sql = self._draft(question, self._SUBQUERY_INSTRUCTION)

        candidates = [join_sql, subquery_sql]
        outcomes = [self.execute(sql) for sql in candidates]

        # Return the first candidate that executed successfully AND is non-empty;
        # if both are non-empty this naturally returns the first one.
        for sql, outcome in zip(candidates, outcomes):
            if outcome.get("ok") and outcome.get("rows"):
                return sql

        # Neither returned rows: prefer a candidate that at least ran cleanly.
        for sql, outcome in zip(candidates, outcomes):
            if outcome.get("ok"):
                return sql

        # Both failed to execute: best-effort fallback to the first draft.
        return join_sql

    def _draft(self, question: str, instruction: str) -> str:
        system = (
            "You are an expert SQLite query writer. Given a database schema and "
            "a natural-language question, output exactly one SQL query and "
            "nothing else."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Instruction: {instruction}\n\n"
            "Return only the SQL query."
        )
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""
        return bridge.extract_sql(response)