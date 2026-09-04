"""A harness that generates two independent SQL formulations (join-based and subquery-based), executes both, and returns the SQL string from the non-empty result (or the first if both are non-empty)."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS0TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # First formulation: join-based query
        join_prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a SQL query that uses explicit JOINs to answer the question. "
            f"Return only the SQL query, no explanation."
        )
        join_response = self.llm(join_prompt, system="", temperature=0.0, n=1)
        join_sql = bridge.extract_sql(join_response)

        # Second formulation: subquery-based query
        subquery_prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a SQL query that uses subqueries (nested SELECTs) to answer the question. "
            f"Return only the SQL query, no explanation."
        )
        subquery_response = self.llm(subquery_prompt, system="", temperature=0.0, n=1)
        subquery_sql = bridge.extract_sql(subquery_response)

        # Execute both queries
        join_result = self.execute(join_sql)
        subquery_result = self.execute(subquery_sql)

        # Determine which result to use
        join_has_rows = join_result.get("ok", False) and bool(join_result.get("rows", []))
        subquery_has_rows = subquery_result.get("ok", False) and bool(subquery_result.get("rows", []))

        if join_has_rows and not subquery_has_rows:
            return join_sql
        elif subquery_has_rows and not join_has_rows:
            return subquery_sql
        elif join_has_rows and subquery_has_rows:
            # Both have results, return the first (join-based)
            return join_sql
        else:
            # Both empty or error, return the first formulation as fallback
            return join_sql