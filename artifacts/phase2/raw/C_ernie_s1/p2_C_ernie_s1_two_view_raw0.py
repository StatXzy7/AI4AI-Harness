"""Generates two independent SQL formulations (join-based and subquery-based), executes both, and returns the first non-empty result or the first if both are non-empty."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2CErnieS1TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # First formulation: join-based approach
        join_prompt = f"""Given the following database schema:
{self.schema}

Write a SQL query to answer: {question}
Use JOIN operations to combine tables where needed.
Return only the SQL query, no explanations."""
        
        # Second formulation: subquery-based approach
        subquery_prompt = f"""Given the following database schema:
{self.schema}

Write a SQL query to answer: {question}
Use subqueries (nested SELECT statements) where appropriate.
Return only the SQL query, no explanations."""
        
        # Generate two independent SQL formulations
        join_text = self.llm(join_prompt, system="", temperature=0.0, n=1)
        subquery_text = self.llm(subquery_prompt, system="", temperature=0.0, n=1)
        
        # Extract SQL from each formulation
        join_sql = bridge.extract_sql(join_text)
        subquery_sql = bridge.extract_sql(subquery_text)
        
        # Execute both SQL queries
        join_result = self.execute(join_sql)
        subquery_result = self.execute(subquery_sql)
        
        # Determine which result to return based on the strategy
        join_has_rows = join_result.get("ok", False) and len(join_result.get("rows", [])) > 0
        subquery_has_rows = subquery_result.get("ok", False) and len(subquery_result.get("rows", [])) > 0
        
        # Return the first non-empty result, or the first if both are non-empty
        if join_has_rows and not subquery_has_rows:
            return join_sql
        elif subquery_has_rows and not join_has_rows:
            return subquery_sql
        else:
            # Both have rows or both are empty - return the first (join-based)
            return join_sql