"""Generates two independent SQL formulations (join-based and subquery-based), executes both, and returns the one yielding non-empty results (or the first if both do)."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2DErnieS0TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # First formulation: join-based
        prompt_join = (
            f"Schema: {self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query using JOINs to answer the question. "
            "Return only the SQL, no explanation."
        )
        response_join = self.llm(prompt_join, system="", temperature=0.0, n=1)
        sql_join = bridge.extract_sql(response_join)

        # Second formulation: subquery-based
        prompt_subquery = (
            f"Schema: {self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query using subqueries to answer the question. "
            "Return only the SQL, no explanation."
        )
        response_subquery = self.llm(prompt_subquery, system="", temperature=0.0, n=1)
        sql_subquery = bridge.extract_sql(response_subquery)

        # Execute both formulations
        result_join = self.execute(sql_join)
        result_subquery = self.execute(sql_subquery)

        # Helper to check if a result is non-empty (ok and has rows)
        def is_non_empty(res):
            return res.get("ok", False) and len(res.get("rows", [])) > 0

        # Decide which SQL to return based on results
        if is_non_empty(result_join) and not is_non_empty(result_subquery):
            return sql_join
        elif is_non_empty(result_subquery) and not is_non_empty(result_join):
            return sql_subquery
        elif is_non_empty(result_join) and is_non_empty(result_subquery):
            # Both non-empty: return the first (join-based)
            return sql_join
        else:
            # Neither is non-empty: fallback to the first formulation
            return sql_join