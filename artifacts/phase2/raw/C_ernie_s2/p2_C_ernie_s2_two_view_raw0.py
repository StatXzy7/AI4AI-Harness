"""Generates two independent SQL formulations (join-based and subquery-based), executes both, and returns the non-empty result's SQL or the first if both yield rows."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # First formulation: join-based
        join_prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a SQL query that uses explicit JOINs to answer the question. "
            f"Output only the SQL query, no explanations."
        )
        join_text = self.llm(join_prompt, system="", temperature=0.0, n=1)
        join_sql = bridge.extract_sql(join_text)
        
        # Second formulation: subquery-based
        subquery_prompt = (
            f"Given the following database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a SQL query that uses subqueries (nested SELECTs) to answer the question. "
            f"Output only the SQL query, no explanations."
        )
        subquery_text = self.llm(subquery_prompt, system="", temperature=0.0, n=1)
        subquery_sql = bridge.extract_sql(subquery_text)
        
        # Execute both formulations
        join_result = self.execute(join_sql)
        subquery_result = self.execute(subquery_sql)
        
        # Determine which result to return
        join_has_rows = join_result.get("ok", False) and len(join_result.get("rows", [])) > 0
        subquery_has_rows = subquery_result.get("ok", False) and len(subquery_result.get("rows", [])) > 0
        
        if join_has_rows and not subquery_has_rows:
            return join_sql
        elif subquery_has_rows and not join_has_rows:
            return subquery_sql
        elif join_has_rows and subquery_has_rows:
            # Both non-empty: return the first (join-based)
            return join_sql
        else:
            # Both empty: return the first (join-based) as fallback
            return join_sql