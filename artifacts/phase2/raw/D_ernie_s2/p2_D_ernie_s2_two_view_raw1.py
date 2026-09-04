"""Generates two independent SQL formulations (join‑based and subquery‑based), executes both, and returns the first non‑empty result's SQL."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # ---------- First formulation: JOIN‑based ----------
        join_prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a SQL query that answers the question using explicit JOINs. "
            f"Return only the SQL statement."
        )
        join_text = self.llm(join_prompt, system="", temperature=0.0, n=1)
        join_sql = bridge.extract_sql(join_text)

        # Execute the join‑based query
        join_result = self.execute(join_sql)
        join_ok = join_result.get("ok", False) and len(join_result.get("rows", [])) > 0

        # ---------- Second formulation: SUBQUERY‑based ----------
        sub_prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a SQL query that answers the question using subqueries (nested SELECTs). "
            f"Return only the SQL statement."
        )
        sub_text = self.llm(sub_prompt, system="", temperature=0.0, n=1)
        sub_sql = bridge.extract_sql(sub_text)

        # Execute the subquery‑based query
        sub_result = self.execute(sub_sql)
        sub_ok = sub_result.get("ok", False) and len(sub_result.get("rows", [])) > 0

        # ---------- Choose the result ----------
        if join_ok:
            return join_sql
        if sub_ok:
            return sub_sql
        # If neither produced rows, fall back to the first formulation (may be empty)
        return join_sql