"""Two-view harness: the question is independently translated into a JOIN-based draft and a nested-subquery draft, both drafts are executed, and the first draft whose result set is non-empty is returned."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS0TwoView(SQLHarness):
    """Two independently drafted SQL views (join form, subquery form) executed head-to-head."""

    name = "p2p_2d_glm_s0_twoview"

    SYSTEM_PROMPT = (
        "You are a precise text-to-SQL engine targeting SQLite. "
        "Use only the tables and columns that appear in the given schema. "
        "Answer with exactly one SQL SELECT statement and nothing else: "
        "no explanation, no markdown fences, no commentary."
    )

    JOIN_VIEW_PROMPT = (
        "Write the query in JOIN form: list every needed table in the FROM clause and combine "
        "them with explicit JOIN ... ON clauses, keeping the whole answer one flat query. "
        "Do not use nested subqueries (no IN (SELECT ...), no EXISTS, no scalar subqueries) "
        "unless a join genuinely cannot express the question."
    )

    SUBQUERY_VIEW_PROMPT = (
        "Write the query in SUBQUERY form: nest SELECT statements -- IN (SELECT ...), NOT IN, "
        "EXISTS, or scalar subqueries -- to filter one table against another instead of joining "
        "them. Do not use explicit JOIN clauses unless a subquery genuinely cannot express "
        "the question."
    )

    def _draft(self, question: str, style_prompt: str) -> str:
        """Make one independent LLM call and extract a single SQL statement from it."""
        prompt = (
            "Database schema:\n"
            f"{self.schema or ''}\n\n"
            f"Question: {question}\n\n"
            f"{style_prompt}\n\n"
            "SQL:"
        )
        raw = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        if isinstance(raw, (list, tuple)):  # tolerate n>1-style list returns
            raw = raw[0] if raw else ""
        elif isinstance(raw, dict):  # tolerate wrapped completions
            raw = raw.get("text") or raw.get("content") or ""
        if not isinstance(raw, str):
            raw = ""
        return (bridge.extract_sql(raw) or "").strip()

    def _run(self, sql: str) -> dict:
        """Execute one candidate without ever raising; any failure becomes ok=False."""
        if not sql:
            return {"ok": False, "rows": [], "error": "no candidate SQL produced"}
        try:
            result = self.execute(sql)
        except Exception as exc:  # keep the two-view control flow alive no matter what
            return {"ok": False, "rows": [], "error": f"execution error: {exc}"}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": f"unexpected executor response: {result!r}"}
        return result

    @staticmethod
    def _nonempty(result: dict) -> bool:
        """True iff a candidate ran cleanly and returned at least one row."""
        return bool(result) and bool(result.get("ok")) and len(result.get("rows") or []) > 0

    def solve(self, question: str) -> str:
        # View 1 -- independent JOIN-based formulation.
        join_sql = self._draft(question, self.JOIN_VIEW_PROMPT)

        # View 2 -- independent nested-subquery formulation.
        subq_sql = self._draft(question, self.SUBQUERY_VIEW_PROMPT)

        # Execute both views against the database.
        join_res = self._run(join_sql)
        subq_res = self._run(subq_sql)

        # Selection: the first view with a non-empty result set wins; when both are
        # non-empty that is the join view, i.e. the first one.
        if self._nonempty(join_res):
            return join_sql
        if self._nonempty(subq_res):
            return subq_sql

        # Neither view returned rows: keep the first view that at least executes
        # cleanly, otherwise the first draft we managed to produce at all.
        if join_sql and join_res.get("ok"):
            return join_sql
        if subq_sql and subq_res.get("ok"):
            return subq_sql
        return join_sql or subq_sql or ""