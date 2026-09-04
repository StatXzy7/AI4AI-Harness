"""Generates two independent SQL formulations (join‑based and subquery‑based), executes both, and returns the first that yields non‑empty results."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Solve the Text‑to‑SQL task by producing two independent SQL candidates,
        executing each, and returning the first candidate that produces a
        non‑empty result set (or the first candidate if both are non‑empty).
        """
        # ---------- Formulation 1: JOIN‑based ----------
        join_prompt = (
            f"Given the schema:\n{self.schema}\n\n"
            f"Write a SQL query that answers the following question using JOINs only: {question}"
        )
        try:
            join_response = self.llm(join_prompt, system="", temperature=0.0, n=1)
            sql_join = bridge.extract_sql(join_response)
        except Exception:
            sql_join = ""

        # ---------- Formulation 2: SUBQUERY‑based ----------
        sub_prompt = (
            f"Given the schema:\n{self.schema}\n\n"
            f"Write a SQL query that answers the following question using subqueries (no explicit JOINs): {question}"
        )
        try:
            sub_response = self.llm(sub_prompt, system="", temperature=0.0, n=1)
            sql_sub = bridge.extract_sql(sub_response)
        except Exception:
            sql_sub = ""

        # ---------- Execute both candidates ----------
        def _has_rows(res):
            return res.get("ok") and isinstance(res.get("rows"), list) and len(res["rows"]) > 0

        res_join = self.execute(sql_join) if sql_join else {"ok": False, "rows": []}
        res_sub = self.execute(sql_sub) if sql_sub else {"ok": False, "rows": []}

        # ---------- Choose result ----------
        if _has_rows(res_join):
            return sql_join
        if _has_rows(res_sub):
            return sql_sub

        # If neither yields rows, return an empty string (fallback)
        return ""