"""Harness that solves Text-to-SQL by generating two independent SQL formulations (JOIN-based and subquery-based), executing both, and returning the first query whose result is non-empty."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS0TwoView(SQLHarness):
    """Two-view harness: writes the SQL from two independent formulations,
    executes both, and returns the result that is non-empty (or, if both are
    non-empty, the first one)."""

    def solve(self, question: str) -> str:
        schema = self.schema

        # ---- View 1: join-based formulation (independent) ----
        prompt_join = (
            "You are given the following database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single valid SQLite SQL query that answers the question. "
            "Formulate it using explicit JOIN clauses between tables wherever "
            "multiple tables are needed; do NOT use subqueries. "
            "Output only the SQL query, nothing else."
        )
        text_join = self.llm(
            prompt_join,
            system="You are a careful Text-to-SQL assistant that writes join-based SQL.",
            temperature=0.0,
            n=1,
        )
        sql_join = bridge.extract_sql(text_join)

        # ---- View 2: subquery-based formulation (independent) ----
        prompt_sub = (
            "You are given the following database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single valid SQLite SQL query that answers the question. "
            "Formulate it using nested subqueries (e.g. IN, EXISTS, or scalar "
            "subqueries in the WHERE clause) instead of explicit JOIN clauses "
            "wherever multiple tables are needed. "
            "Output only the SQL query, nothing else."
        )
        text_sub = self.llm(
            prompt_sub,
            system="You are a careful Text-to-SQL assistant that writes subquery-based SQL.",
            temperature=0.0,
            n=1,
        )
        sql_sub = bridge.extract_sql(text_sub)

        # ---- Execute both formulations ----
        if sql_join:
            res_join = self.execute(sql_join)
        else:
            res_join = {"ok": False, "rows": [], "error": "no sql extracted"}

        if sql_sub:
            res_sub = self.execute(sql_sub)
        else:
            res_sub = {"ok": False, "rows": [], "error": "no sql extracted"}

        join_nonempty = bool(res_join.get("ok")) and bool(res_join.get("rows"))
        sub_nonempty = bool(res_sub.get("ok")) and bool(res_sub.get("rows"))

        # ---- Selection: non-empty result wins; if both, the first wins ----
        if join_nonempty:
            return sql_join
        if sub_nonempty:
            return sql_sub

        # Both empty or failed: prefer a query that at least executed cleanly.
        if res_join.get("ok"):
            return sql_join
        if res_sub.get("ok"):
            return sql_sub

        # Last resort: return whatever was generated.
        return sql_join or sql_sub or ""