"""Two-view SQL harness: generates two independent SQL formulations, executes both, returns the one that yields rows."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # Build two distinct system prompts encouraging different formulations
        schema = self.schema or ""

        system_join = (
            "You are a SQL expert. Given the database schema and the user's question, "
            "produce exactly one SQL query using JOINs to combine relevant tables. "
            "Return only the SQL statement with no explanation and no markdown."
        )

        system_subq = (
            "You are a SQL expert. Given the database schema and the user's question, "
            "produce exactly one SQL query using subqueries (WHERE IN / SELECT subquery) "
            "rather than JOINs to retrieve the answer. "
            "Return only the SQL statement with no explanation and no markdown."
        )

        # Generate view A: join-based
        view_a_raw = self.llm(question, system=system_join, temperature=0.0, n=1)
        sql_a = bridge.extract_sql(view_a_raw)

        # Generate view B: subquery-based
        view_b_raw = self.llm(question, system=system_subq, temperature=0.0, n=1)
        sql_b = bridge.extract_sql(view_b_raw)

        # Execute both; prefer the non-empty result, fall back to sql_a if both empty/error
        res_a = None
        res_b = None

        if sql_a:
            res_a = self.execute(sql_a)
        if sql_b:
            res_b = self.execute(sql_b)

        a_ok = bool(res_a and res_a.get("ok") and res_a.get("rows"))
        b_ok = bool(res_b and res_b.get("ok") and res_b.get("rows"))

        if a_ok and not b_ok:
            return sql_a
        if b_ok and not a_ok:
            return sql_b
        # Both non-empty: return first
        if a_ok and b_ok:
            return sql_a

        # Both empty or only one was extractable: fall back to whichever we have
        if sql_a:
            return sql_a
        if sql_b:
            return sql_b
        # Last resort: return whatever raw text we got
        return view_a_raw or view_b_raw or ""