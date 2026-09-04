"""Generates two independent SQL formulations (join-based and subquery-based), executes both, and returns the first non-empty result or the first if both are non-empty."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS1TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # First view: join-based formulation
        join_prompt = (
            f"Given the following database schema and question, write a SQL query using JOIN operations "
            f"to answer the question. Return only the SQL query.\n\n"
            f"Schema: {self.schema}\n\n"
            f"Question: {question}\n\n"
            f"SQL:"
        )
        join_text = self.llm(join_prompt, system="", temperature=0.0, n=1)
        join_sql = bridge.extract_sql(join_text)
        
        # Second view: subquery-based formulation
        subquery_prompt = (
            f"Given the following database schema and question, write a SQL query using subqueries "
            f"to answer the question. Return only the SQL query.\n\n"
            f"Schema: {self.schema}\n\n"
            f"Question: {question}\n\n"
            f"SQL:"
        )
        subquery_text = self.llm(subquery_prompt, system="", temperature=0.0, n=1)
        subquery_sql = bridge.extract_sql(subquery_text)
        
        # Execute both formulations
        join_result = self.execute(join_sql)
        subquery_result = self.execute(subquery_sql)
        
        # Determine which result to return based on non-empty rows
        if join_result["ok"] and join_result["rows"]:
            return join_sql
        elif subquery_result["ok"] and subquery_result["rows"]:
            return subquery_sql
        else:
            # If both are empty or failed, return the first (join-based) as fallback
            return join_sql