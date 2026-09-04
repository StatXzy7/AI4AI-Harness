"""Two independent SQL formulations of the same question (a JOIN-based view and a SUBQUERY-based view) are generated, both executed against the database, and the first formulation whose result set is non-empty is returned."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS1TwoView"]


class P2P2DGlmS1TwoView(SQLHarness):
    """Two-view weak solver for Text-to-SQL.

    Mechanism:
      1. View 1 (join view): the question is translated with an explicit
         JOIN-based formulation bias.
      2. View 2 (subquery view): the question is translated *independently*
         with an explicit SUBQUERY-based formulation bias; neither view ever
         sees the other's output.
      3. Both candidate queries are executed against the database.
      4. Selection: the first candidate whose execution succeeded AND returned
         at least one row is returned. Iterating in candidate order guarantees
         that when both are non-empty the FIRST (join-based) view wins. If
         neither returns rows, the first candidate that at least executed
         cleanly is returned; otherwise the first view is returned as-is.
    """

    SYSTEM_PROMPT = (
        "You are an expert SQLite translator. Reply with exactly one "
        "executable SQL query and nothing else."
    )

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        schema = (self.schema or "").strip()

        # --- View 1: JOIN-based formulation (independent generation) ------
        join_sql = self._generate(self._view_prompt(question, schema, view="join"))

        # --- View 2: SUBQUERY-based formulation (independent generation) --
        # Generated from a separate prompt so the two views stay independent.
        subquery_sql = self._generate(
            self._view_prompt(question, schema, view="subquery")
        )

        candidates = [join_sql, subquery_sql]

        # --- Execute BOTH formulations -------------------------------------
        outcomes = [self._safe_execute(sql) for sql in candidates]

        # --- Selection ------------------------------------------------------
        # First candidate with a non-empty result set wins; scanning in order
        # means that if BOTH are non-empty, the FIRST (join-based) one is
        # returned.
        for sql, outcome in zip(candidates, outcomes):
            if sql and self._has_rows(outcome):
                return sql

        # Neither formulation produced rows. Final tiebreak: prefer the first
        # candidate that at least executed without error...
        for sql, outcome in zip(candidates, outcomes):
            if sql and outcome.get("ok"):
                return sql

        # ...otherwise fall back to the first view (possibly empty string).
        for sql in candidates:
            if sql:
                return sql
        return candidates[0]

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #
    def _view_prompt(self, question: str, schema: str, view: str) -> str:
        if view == "join":
            bias = (
                "Formulation constraint: write a JOIN-BASED query. Whenever data "
                "must be combined across tables, use explicit JOIN ... ON "
                "clauses (or comma-separated tables with WHERE join predicates). "
                "Do NOT use nested SELECT subqueries."
            )
        else:
            bias = (
                "Formulation constraint: write a SUBQUERY-BASED query. Express "
                "the answer using nested SELECT subqueries -- e.g. "
                "'IN (SELECT ...)' filters, scalar subqueries, or comparisons "
                "against aggregated subqueries -- instead of JOIN clauses "
                "wherever possible."
            )
        return (
            "Database schema:\n"
            f"{schema or '(no schema provided)'}\n\n"
            f"Question: {question}\n\n"
            f"{bias}\n"
            "Output only the SQL query."
        )

    # ------------------------------------------------------------------ #
    # Generation helper
    # ------------------------------------------------------------------ #
    def _generate(self, prompt: str) -> str:
        """One LLM call -> extracted SQL string ('' on any failure)."""
        try:
            raw = self.llm(prompt, system=self.SYSTEM_PROMPT,
                           temperature=0.0, n=1)
        except Exception:
            return ""

        text = self._first_text(raw)
        if not text:
            return ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""
        sql = (sql or "").strip()
        # If extraction yields nothing usable, fall back to the raw reply.
        return sql if sql else text.strip()

    # ------------------------------------------------------------------ #
    # Execution helpers
    # ------------------------------------------------------------------ #
    def _safe_execute(self, sql: str) -> dict:
        """Execute a candidate without ever raising; always returns a dict."""
        if not sql:
            return {"ok": False, "rows": [], "error": "no SQL produced"}
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "malformed execution result"}
        result.setdefault("ok", False)
        result.setdefault("rows", [])
        result.setdefault("error", "")
        return result

    @staticmethod
    def _has_rows(outcome: dict) -> bool:
        """True only if execution succeeded AND returned at least one row."""
        return bool(outcome.get("ok")) and len(outcome.get("rows") or []) > 0

    @staticmethod
    def _first_text(raw) -> str:
        """Normalize an LLM reply (which may be a string or a list) to text."""
        if isinstance(raw, (list, tuple)):
            for item in raw:
                if item:
                    return str(item)
            return ""
        return str(raw) if raw else ""