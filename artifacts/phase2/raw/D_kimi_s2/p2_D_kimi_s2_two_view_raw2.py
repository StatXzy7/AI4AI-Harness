"""Draft SQL from two independent formulations (join-based and subquery-based), execute both, and return the first query whose execution yields a non-empty result (ties and failures fall back to the first formulation)."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2TwoView(SQLHarness):
    """Two-view Text-to-SQL harness around a frozen weak solver.

    Control flow:
      1. Ask the LLM for a JOIN-based formulation of the answer.
      2. Ask the LLM, independently, for a subquery-based formulation.
      3. Execute both candidate queries against the database.
      4. Return the first candidate that executes successfully and returns
         at least one row; if both do, return the first (join-based) one.
         If neither returns rows, prefer a query that at least executed
         cleanly (an empty answer may be correct), otherwise fall back to
         the raw first draft.
    """

    _JOIN_SYSTEM = (
        "You are an expert SQLite programmer. "
        "You answer questions with a single SQL query and nothing else."
    )

    _SUBQUERY_SYSTEM = (
        "You are an expert SQLite programmer who favours nested subqueries. "
        "You answer questions with a single SQL query and nothing else."
    )

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _ask(self, prompt: str, system: str) -> str:
        """Call the frozen LLM and normalise the response to a string."""
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out or ""

    def _draft(self, question: str, view: str) -> str:
        """Generate one candidate SQL query for the given formulation view."""
        if view == "join":
            system = self._JOIN_SYSTEM
            style = (
                "Formulate the answer as a JOIN-based query: navigate the "
                "schema with explicit JOIN ... ON clauses between the "
                "relevant tables, and avoid subqueries unless they are "
                "strictly required."
            )
        else:
            system = self._SUBQUERY_SYSTEM
            style = (
                "Formulate the answer as a subquery-based query: keep a "
                "single outer SELECT over one table and express all "
                "cross-table conditions with nested subqueries (IN, EXISTS, "
                "or scalar comparisons) instead of explicit JOINs whenever "
                "possible."
            )

        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"{style}\n\n"
            "Return only the SQL query, with no explanation or commentary."
        )
        return bridge.extract_sql(self._ask(prompt, system))

    def _run(self, sql: str) -> dict:
        """Execute a candidate query defensively, returning a result dict."""
        if not sql or not sql.strip():
            return {"ok": False, "rows": [], "error": "empty sql"}
        try:
            res = self.execute(sql)
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "rows": [], "error": str(exc)}
        if not isinstance(res, dict):
            return {"ok": False, "rows": [], "error": "malformed result"}
        res.setdefault("ok", False)
        res.setdefault("rows", [])
        res.setdefault("error", "")
        return res

    @staticmethod
    def _non_empty(res: dict) -> bool:
        """True iff the execution succeeded and returned at least one row."""
        return bool(res.get("ok")) and bool(res.get("rows"))

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # Step 1 & 2: two independent formulations of the same question.
        sql_join = self._draft(question, "join")
        sql_subq = self._draft(question, "subquery")

        # Step 3: execute both candidates.
        res_join = self._run(sql_join)
        res_subq = self._run(sql_subq)

        # Step 4: first non-empty result wins; a tie goes to the first view.
        if self._non_empty(res_join):
            return sql_join
        if self._non_empty(res_subq):
            return sql_subq

        # Fallbacks: prefer a cleanly executing (but empty) query, else the
        # first formulation regardless of its execution error.
        if res_join.get("ok"):
            return sql_join
        if res_subq.get("ok"):
            return sql_subq
        return sql_join or sql_subq