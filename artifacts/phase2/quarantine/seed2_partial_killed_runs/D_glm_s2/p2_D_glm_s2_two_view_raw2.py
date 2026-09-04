"""Two independent SQL formulations of the question (a JOIN-based view and a subquery-based view) are generated and both executed, returning the first formulation whose execution produced rows and falling back to the first formulation when neither does."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2TwoView"]


class P2P2DGlmS2TwoView(SQLHarness):
    """Two-view (join-based vs. subquery-based) dual-formulation harness.

    The strategy is realized in the control flow of `solve`, not just in the
    prompts:
      1. two independent LLM calls produce two structurally different
         candidate SQL statements for the same question (one join-based,
         one subquery-based);
      2. both candidates are executed against the database;
      3. the candidate whose execution returned rows is returned; if both
         returned rows, or neither did, the first candidate is returned.
    """

    NAME = "p2p2d_glm_s2_two_view"

    JOIN_SYSTEM = (
        "You are an expert text-to-SQL solver. Answer the user's question with "
        "exactly one SQLite SELECT statement that uses explicit JOIN clauses "
        "(INNER JOIN / LEFT JOIN ... ON ...) whenever data from more than one "
        "table is needed. Do NOT use nested or correlated subqueries. Output "
        "only the SQL statement and nothing else."
    )

    SUBQUERY_SYSTEM = (
        "You are an expert text-to-SQL solver. Answer the user's question with "
        "exactly one SQLite SELECT statement that uses nested subqueries (IN, "
        "NOT IN, EXISTS, NOT EXISTS, or scalar subqueries inside WHERE/HAVING) "
        "whenever data from more than one table is needed. Do NOT use the JOIN "
        "keyword at all. Output only the SQL statement and nothing else."
    )

    def solve(self, question: str) -> str:
        # ---- Step 1: two independent formulations of the same question ----
        join_sql = self._formulate(question, self.JOIN_SYSTEM)
        subquery_sql = self._formulate(question, self.SUBQUERY_SYSTEM)

        # Degenerate cases where generation/extraction failed outright.
        if not join_sql and not subquery_sql:
            return ""
        if not join_sql:
            return subquery_sql
        if not subquery_sql:
            return join_sql

        # ---- Step 2: execute BOTH candidates (no short-circuiting) ----
        join_out = self._safe_execute(join_sql)
        subquery_out = self._safe_execute(subquery_sql)

        join_nonempty = bool(join_out.get("ok")) and bool(join_out.get("rows"))
        subquery_nonempty = bool(subquery_out.get("ok")) and bool(subquery_out.get("rows"))

        # ---- Step 3: the non-empty result wins; the first wins ties and
        #              total failure (both empty / both erroring) ----
        if subquery_nonempty and not join_nonempty:
            return subquery_sql
        return join_sql

    # ---------------------------------------------------------------------
    # helpers
    # ---------------------------------------------------------------------

    def _formulate(self, question: str, system: str) -> str:
        """One independent LLM call in the requested style -> cleaned SQL (or '')."""
        schema = getattr(self, "schema", None) or ""
        prompt = (
            "Database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. "
            "Output only the SQL query."
        )
        try:
            text = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        if isinstance(text, (list, tuple)):  # defensive: n>1-style returns
            text = text[0] if text else ""
        if not isinstance(text, str) or not text.strip():
            return ""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            return ""
        sql = (sql or "").strip()
        if sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    def _safe_execute(self, sql: str) -> dict:
        """Execute a candidate without ever raising; always returns a result dict."""
        try:
            out = self.execute(sql)
        except Exception:
            return {"ok": False, "rows": [], "error": "execution raised"}
        if not isinstance(out, dict):
            return {"ok": False, "rows": [], "error": "unexpected execute payload"}
        return out