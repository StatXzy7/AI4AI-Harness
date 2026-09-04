"""Generate two independent SQL formulations of the question (a flat JOIN-based query and a nested subquery-based query), execute both against the database, and return the query whose result set is non-empty, preferring the first (JOIN-based) formulation when both succeed."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS0TwoView"]


class P2P2CGlmS0TwoView(SQLHarness):
    """Two-view text-to-SQL harness: join-style vs. subquery-style, selected by executed rows."""

    NAME = "P2P2CGlmS0TwoView"
    FALLBACK_SQL = "SELECT 1;"  # benign stub, used only if both views fail to produce any SQL

    # ---- View 1: flat, join-based formulation ------------------------- #
    JOIN_VIEW_SYSTEM = (
        "You are a precise text-to-SQL translator for SQLite. "
        "Answer with exactly one SELECT statement written in a flat, join-based style: "
        "combine the required tables with explicit JOIN ... ON clauses (or comma-separated "
        "tables with the join conditions in the WHERE clause). "
        "Do not use nested subqueries. "
        "Use only tables and columns that appear in the provided schema. "
        "Reply with the SQL statement only: no explanation, no markdown fences."
    )

    # ---- View 2: independent, nested subquery-based formulation ------- #
    SUBQUERY_VIEW_SYSTEM = (
        "You are a precise text-to-SQL translator for SQLite. "
        "Answer with exactly one SELECT statement written in a nested, subquery-based style: "
        "express the logic with IN (...), NOT IN (...), EXISTS (...), or scalar/derived-table "
        "subqueries instead of JOIN clauses wherever possible. "
        "Use only tables and columns that appear in the provided schema. "
        "Reply with the SQL statement only: no explanation, no markdown fences."
    )

    USER_TEMPLATE = (
        "Database schema:\n"
        "{schema}\n\n"
        "Question: {question}\n\n"
        "Respond with a single SQLite SELECT statement and nothing else."
    )

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _generate(self, question: str, system: str) -> str:
        """Produce one independent SQL formulation of `question` under the given style."""
        prompt = self.USER_TEMPLATE.format(schema=self.schema, question=question)
        try:
            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            raw = ""
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        raw = "" if raw is None else str(raw)
        if not raw.strip():
            return ""
        try:
            sql = bridge.extract_sql(raw)
        except Exception:
            sql = ""
        return (sql or "").strip()

    def _execute(self, sql: str) -> dict:
        """Execute `sql` defensively and normalise the outcome to {ok, rows, error}."""
        if not sql:
            return {"ok": False, "rows": [], "error": "no SQL produced"}
        try:
            out = self.execute(sql)
        except Exception as exc:  # defensive: executor should not raise, but never crash
            return {"ok": False, "rows": [], "error": str(exc)}
        if not isinstance(out, dict):
            return {"ok": False, "rows": [], "error": "unexpected executor output"}
        return {
            "ok": bool(out.get("ok", False)),
            "rows": out.get("rows") or [],
            "error": str(out.get("error") or ""),
        }

    @staticmethod
    def _has_rows(result: dict) -> bool:
        """A view 'has a result' only if it executed cleanly and returned at least one row."""
        return bool(result["ok"]) and len(result["rows"]) > 0

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        # View 1: flat, join-based formulation of the question.
        join_sql = self._generate(question, self.JOIN_VIEW_SYSTEM)

        # View 2: independent, subquery-based formulation of the same question.
        subquery_sql = self._generate(question, self.SUBQUERY_VIEW_SYSTEM)

        # Execute both views against the live database.
        join_outcome = self._execute(join_sql)
        subquery_outcome = self._execute(subquery_sql)

        join_nonempty = self._has_rows(join_outcome)
        subquery_nonempty = self._has_rows(subquery_outcome)

        # Selection rule: return the view whose result is non-empty; if both
        # views are non-empty, the first (join-based) view wins.
        if join_nonempty:
            return join_sql
        if subquery_nonempty:
            return subquery_sql

        # Neither view returned rows: prefer the first query that at least
        # executes cleanly, then the first produced SQL, then a benign stub.
        if join_outcome["ok"]:
            return join_sql
        if subquery_outcome["ok"]:
            return subquery_sql
        return join_sql or subquery_sql or self.FALLBACK_SQL