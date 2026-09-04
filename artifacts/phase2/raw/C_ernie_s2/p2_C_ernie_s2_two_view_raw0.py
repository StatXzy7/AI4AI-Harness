"""Generates two independent SQL formulations (join-based and subquery-based) via separate LLM calls, executes both, and returns the SQL whose result is non-empty (or the first if both succeed)."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # First view: join-based formulation
        join_prompt = (
            f"Given the following database schema:\n\n{self.schema}\n\n"
            f"Write a single SQL query that answers the question below. "
            f"Use explicit JOIN syntax (INNER JOIN / LEFT JOIN) to combine tables. "
            f"Do NOT use subqueries in the FROM or WHERE clause. "
            f"Only output the SQL, nothing else.\n\n"
            f"Question: {question}"
        )
        join_text = self.llm(join_prompt, system="", temperature=0.0, n=1)
        join_sql = bridge.extract_sql(join_text)

        # Second view: subquery-based formulation
        subquery_prompt = (
            f"Given the following database schema:\n\n{self.schema}\n\n"
            f"Write a single SQL query that answers the question below. "
            f"Use subqueries (in WHERE, FROM, or SELECT clauses) rather than flat JOINs. "
            f"Do NOT use plain JOIN syntax; prefer nested SELECTs or IN/EXISTS patterns. "
            f"Only output the SQL, nothing else.\n\n"
            f"Question: {question}"
        )
        subquery_text = self.llm(subquery_prompt, system="", temperature=0.0, n=1)
        subquery_sql = bridge.extract_sql(subquery_text)

        # Execute both formulations
        join_result = self.execute(join_sql)
        subquery_result = self.execute(subquery_sql)

        # Determine which result to return based on non-emptiness
        join_ok = join_result.get("ok", False)
        subquery_ok = subquery_result.get("ok", False)
        join_rows = join_result.get("rows", [])
        subquery_rows = subquery_result.get("rows", [])

        # Prefer non-empty results; if both non-empty, return the first (join-based)
        if join_ok and len(join_rows) > 0:
            return join_sql
        elif subquery_ok and len(subquery_rows) > 0:
            return subquery_sql
        elif join_ok:
            return join_sql
        elif subquery_ok:
            return subquery_sql
        else:
            # Fallback: return the join-based SQL even if it failed
            return join_sql