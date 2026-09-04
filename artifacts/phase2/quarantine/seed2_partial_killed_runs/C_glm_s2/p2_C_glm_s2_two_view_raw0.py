"""This harness compiles the question into two independent SQL views (a JOIN-based formulation and a subquery-based formulation), executes both against the database, and returns the first view whose result set is non-empty, falling back to the join-based view when neither produces rows."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS2TwoView"]


class P2P2CGlmS2TwoView(SQLHarness):
    """Two independent LLM views (JOIN-based and subquery-based) of the same
    question; both are executed and the first non-empty result wins."""

    JOIN_SYSTEM = (
        "You are an expert text-to-SQL engine targeting SQLite. "
        "Translate the user's question into exactly one SQL SELECT statement. "
        "When information from multiple tables is required, combine the tables "
        "with JOIN clauses (or comma-joins in FROM with linking conditions in "
        "WHERE). Do NOT use nested subqueries to combine tables."
    )

    SUBQUERY_SYSTEM = (
        "You are an expert text-to-SQL engine targeting SQLite. "
        "Translate the user's question into exactly one SQL SELECT statement. "
        "When information from multiple tables is required, combine it using "
        "nested subqueries only (IN, NOT IN, EXISTS, NOT EXISTS, or scalar "
        "subqueries in WHERE / FROM). Never use the keyword JOIN."
    )

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #

    def _build_prompt(self, question: str, style_requirement: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"{style_requirement}\n"
            "Output exactly one SQL SELECT statement and nothing else "
            "(no explanation, no markdown, no trailing semicolon)."
        )

    # ------------------------------------------------------------------ #
    # One independent formulation (one "view" of the question)
    # ------------------------------------------------------------------ #

    def _formulate(self, question: str, system: str, style_requirement: str) -> str:
        prompt = self._build_prompt(question, style_requirement)
        try:
            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        # Be tolerant of an executor/LLM that returns a list of completions.
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        text = raw if isinstance(raw, str) else str(raw)
        sql = (bridge.extract_sql(text) or "").strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    # ------------------------------------------------------------------ #
    # Safe execution wrapper
    # ------------------------------------------------------------------ #

    def _execute(self, sql: str) -> dict:
        if not sql:
            return {"ok": False, "rows": [], "error": "no SQL produced"}
        try:
            result = self.execute(sql)
        except Exception as exc:  # executor should not raise, but be safe
            return {"ok": False, "rows": [], "error": str(exc)}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "malformed executor result"}
        result = dict(result)
        result.setdefault("ok", False)
        result.setdefault("rows", [])
        result.setdefault("error", "")
        return result

    @staticmethod
    def _is_nonempty(result: dict) -> bool:
        return bool(result.get("ok")) and len(result.get("rows") or []) > 0

    # ------------------------------------------------------------------ #
    # Strategy: write SQL from two independent formulations, execute both,
    # return the result that is non-empty; if both are, return the first.
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        # --- View 1: join-based formulation ------------------------------ #
        join_sql = self._formulate(
            question,
            system=self.JOIN_SYSTEM,
            style_requirement=(
                "Style requirement: JOIN-based formulation -- combine tables "
                "with JOINs; do not use nested subqueries for table combination."
            ),
        )

        # --- View 2: subquery-based formulation -------------------------- #
        subquery_sql = self._formulate(
            question,
            system=self.SUBQUERY_SYSTEM,
            style_requirement=(
                "Style requirement: subquery-based formulation -- combine "
                "tables with nested subqueries (IN / EXISTS / scalar "
                "subqueries); never use JOIN."
            ),
        )

        # --- Execute both views independently ---------------------------- #
        join_result = self._execute(join_sql)
        subquery_result = self._execute(subquery_sql)

        join_nonempty = self._is_nonempty(join_result)
        subquery_nonempty = self._is_nonempty(subquery_result)

        # --- Selection ---------------------------------------------------- #
        # A non-empty result wins; if both views are non-empty, keep the
        # first (join-based) view.
        if join_nonempty:
            return join_sql
        if subquery_nonempty:
            return subquery_sql

        # Neither view returned rows: prefer whichever at least executed
        # cleanly; otherwise fall back to the first (join-based) candidate.
        if join_result.get("ok") and join_sql:
            return join_sql
        if subquery_result.get("ok") and subquery_sql:
            return subquery_sql
        return join_sql or subquery_sql