"""Two-view harness that generates SQL via two independent formulations, executes both, and returns the non-empty result."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # Formulation A: join-based
        prompt_a = (
            "You are an expert SQL generator. Given the schema and a natural language question, "
            "produce ONE valid SQL query that uses explicit JOIN clauses to combine tables.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return ONLY the SQL statement, no commentary."
        )
        raw_a = self.llm(prompt_a, system="", temperature=0.0, n=1)
        sql_a = bridge.extract_sql(raw_a)

        # Formulation B: subquery-based
        prompt_b = (
            "You are an expert SQL generator. Given the schema and a natural language question, "
            "produce ONE valid SQL query that uses nested subqueries (e.g. WHERE col IN (SELECT ...)) "
            "to answer the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return ONLY the SQL statement, no commentary."
        )
        raw_b = self.llm(prompt_b, system="", temperature=0.0, n=1)
        sql_b = bridge.extract_sql(raw_b)

        # Execute both; prefer the one that returns rows.
        result_a = self.execute(sql_a) if sql_a else {"ok": False, "rows": [], "error": "empty sql"}
        result_b = self.execute(sql_b) if sql_b else {"ok": False, "rows": [], "error": "empty sql"}

        a_rows = result_a.get("rows", []) or []
        b_rows = result_b.get("rows", []) or []

        if a_rows and not b_rows:
            return sql_a
        if b_rows and not a_rows:
            return sql_b
        if a_rows and b_rows:
            return sql_a
        # both empty/failed: return join-based attempt as fallback
        return sql_a if sql_a else (sql_b or "")