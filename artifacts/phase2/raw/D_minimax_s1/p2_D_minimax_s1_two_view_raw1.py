"""Two-view Text-to-SQL harness that writes SQL via a frozen solver, executes two independent formulations, and returns the first query that yields non-empty rows."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS1TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL generator. Given a database schema and a natural "
            "language question, produce exactly one executable SQL statement that answers the "
            "question. Use standard SQL syntax compatible with SQLite. Do not include "
            "explanations, comments, or markdown formatting; respond with only the SQL "
            "statement. When the question can be expressed in multiple ways, prefer joins "
            "over correlated subqueries unless a subquery is clearly more natural."
        )

        formulation_a_prompt = (
            "Formulation A (Join-Based):\n"
            "Express the answer using explicit JOINs between related tables wherever "
            "possible. Prefer INNER JOIN / LEFT JOIN over subqueries in the WHERE or "
            "SELECT clauses. Use table aliases to keep the query readable.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Output the SQL statement only."
        )

        formulation_b_prompt = (
            "Formulation B (Subquery-Based):\n"
            "Express the answer using subqueries (WHERE ... IN (SELECT ...), "
            "EXISTS (SELECT ...), or scalar subqueries in SELECT) rather than explicit "
            "JOINs. Keep the outer query simple and push filtering logic into the "
            "subqueries.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Output the SQL statement only."
        )

        raw_a = self.llm(formulation_a_prompt, system=system, temperature=0.0, n=1)
        raw_b = self.llm(formulation_b_prompt, system=system, temperature=0.0, n=1)

        sql_a = bridge.extract_sql(raw_a)
        sql_b = bridge.extract_sql(raw_b)

        if sql_a:
            res_a = self.execute(sql_a)
            if res_a.get("ok") and res_a.get("rows"):
                return sql_a

        if sql_b:
            res_b = self.execute(sql_b)
            if res_b.get("ok") and res_b.get("rows"):
                return sql_b

        if sql_a and res_a.get("ok"):
            return sql_a
        if sql_b and res_b.get("ok"):
            return sql_b

        return sql_a or sql_b or ""