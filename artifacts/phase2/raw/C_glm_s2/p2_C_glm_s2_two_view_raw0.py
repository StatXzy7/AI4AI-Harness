"""Each question is solved twice with independent SQL formulations -- an explicit-JOIN view and a nested-subquery view -- both candidates are executed, and the first formulation yielding a non-empty result set is returned (falling back to the first statement that executes cleanly)."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS2TwoView(SQLHarness):
    """Two-view text-to-SQL: a join-based formulation and a subquery-based
    formulation are generated independently, both are executed, and the
    non-empty one wins (ties go to the first/join view)."""

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL engine for SQLite. "
        "Reply with exactly one SQL SELECT statement and nothing else."
    )

    JOIN_VIEW_PROMPT = (
        "Database schema:\n"
        "{schema}\n\n"
        "Question: {question}\n\n"
        "Write a single SQLite SELECT statement that answers the question.\n"
        "Mandatory style: JOIN-BASED. Combine tables using explicit "
        "JOIN ... ON clauses. Do NOT use nested subqueries -- no "
        "IN (SELECT ...), no EXISTS (...), and no scalar subqueries.\n"
        "Output only the SQL statement."
    )

    SUBQUERY_VIEW_PROMPT = (
        "Database schema:\n"
        "{schema}\n\n"
        "Question: {question}\n\n"
        "Write a single SQLite SELECT statement that answers the question.\n"
        "Mandatory style: SUBQUERY-BASED. Express relationships between tables "
        "with nested subqueries -- IN (SELECT ...), EXISTS (...), or scalar "
        "subqueries in WHERE/HAVING. Avoid explicit JOIN ... ON clauses "
        "wherever a subquery can do the job.\n"
        "Output only the SQL statement."
    )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _generate_view(self, question: str, template: str) -> str:
        """Ask the frozen LLM for one independent SQL formulation and extract it."""
        prompt = template.format(schema=self.schema or "", question=question)
        try:
            raw = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        except Exception:
            return ""
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        if not isinstance(raw, str):
            raw = str(raw)
        try:
            sql = bridge.extract_sql(raw)
        except Exception:
            sql = raw.strip()
        return (sql or "").strip()

    def _execute_view(self, sql: str) -> dict:
        """Execute a candidate statement; never raises, always returns a result dict."""
        if not sql:
            return {"ok": False, "rows": [], "error": "no SQL produced"}
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: execute() is expected to not raise
            return {"ok": False, "rows": [], "error": str(exc)}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "unexpected execute() result"}
        return result

    @staticmethod
    def _has_rows(result: dict) -> bool:
        """A view 'succeeds' only if it executed without error AND returned rows."""
        return bool(result.get("ok")) and bool(result.get("rows"))

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        # Step 1: two independent formulations of the same question.
        join_sql = self._generate_view(question, self.JOIN_VIEW_PROMPT)
        subquery_sql = self._generate_view(question, self.SUBQUERY_VIEW_PROMPT)

        # Step 2: execute both candidates against the database.
        join_result = self._execute_view(join_sql)
        subquery_result = self._execute_view(subquery_sql)

        join_hits = self._has_rows(join_result)
        subquery_hits = self._has_rows(subquery_result)

        # Step 3: selection -- the non-empty result wins; if both are
        # non-empty, keep the first (join-based) view.
        if join_hits:
            return join_sql
        if subquery_hits:
            return subquery_sql

        # Step 4: degenerate case -- neither view returned rows. Prefer the
        # first statement that at least executes without error; otherwise
        # return the first formulation whatever its fate.
        if join_result.get("ok"):
            return join_sql
        if subquery_result.get("ok"):
            return subquery_sql
        return join_sql or subquery_sql or ""