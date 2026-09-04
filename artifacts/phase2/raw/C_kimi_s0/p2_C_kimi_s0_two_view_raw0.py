"""Harness that drafts the question as two independent SQL formulations (join-based and subquery-based), executes both, and returns the first query yielding a non-empty result."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS0TwoView(SQLHarness):
    """Two-view Text-to-SQL harness.

    The frozen weak solver is prompted twice with two independent
    formulations of the same question: one that must express table
    relationships with explicit JOIN clauses and one that must express
    them with nested subqueries. Both candidate SQL strings are executed,
    and the first candidate whose execution succeeds and returns at least
    one row is returned (the join-based view wins ties); if neither view
    yields rows, a cleanly-executing candidate, or finally the join-based
    draft, is returned as a fallback.
    """

    _JOIN_SYSTEM = (
        "You are an expert SQL engineer. You answer questions with a single "
        "SQL query built primarily from explicit JOIN clauses."
    )
    _SUBQUERY_SYSTEM = (
        "You are an expert SQL engineer. You answer questions with a single "
        "SQL query built primarily from nested subqueries rather than JOINs."
    )

    def _draft_sql(self, question: str, style: str) -> str:
        """Ask the frozen solver for one formulation and extract its SQL."""
        if style == "join":
            system = self._JOIN_SYSTEM
            formulation = (
                "Formulate the answer as ONE SQL query that uses explicit "
                "JOIN ... ON clauses between the relevant tables. Do NOT "
                "use subqueries; express every table relationship as a join."
            )
        else:
            system = self._SUBQUERY_SYSTEM
            formulation = (
                "Formulate the answer as ONE SQL query that uses nested "
                "subqueries (e.g. WHERE col IN (SELECT ...)) to relate "
                "tables. Do NOT use explicit JOIN clauses; express every "
                "table relationship through subqueries."
            )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"{formulation}\n\n"
            "Return only the SQL query, with no explanation or commentary."
        )
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(response)

    @staticmethod
    def _ran_nonempty(result) -> bool:
        """True iff execution succeeded and returned at least one row."""
        return bool(result) and bool(result.get("ok")) and bool(result.get("rows"))

    def solve(self, question: str) -> str:
        # View 1: join-based formulation.
        join_sql = self._draft_sql(question, "join")
        # View 2: subquery-based formulation, prompted independently.
        subquery_sql = self._draft_sql(question, "subquery")

        join_result = (
            self.execute(join_sql)
            if join_sql
            else {"ok": False, "rows": [], "error": "no sql extracted"}
        )
        subquery_result = (
            self.execute(subquery_sql)
            if subquery_sql
            else {"ok": False, "rows": [], "error": "no sql extracted"}
        )

        # Return the first candidate that produced a non-empty result.
        if self._ran_nonempty(join_result):
            return join_sql
        if self._ran_nonempty(subquery_result):
            return subquery_sql

        # Fallbacks: prefer a candidate that at least executed cleanly,
        # then the join-based draft, then whichever draft is non-empty.
        if join_sql and join_result.get("ok"):
            return join_sql
        if subquery_sql and subquery_result.get("ok"):
            return subquery_sql
        return join_sql or subquery_sql