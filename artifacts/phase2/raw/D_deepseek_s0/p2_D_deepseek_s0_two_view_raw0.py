"""Generate two SQL formulations (join-based and subquery-based), execute both, and return the non-empty result preferring the first when both succeed."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2DDeepseekS0TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        prompt_join = f"""Given the following database schema:
{schema}

Question: {question}

Write a SQL query that answers the question using JOINs where possible.
Return only the SQL query without any explanation or markdown."""

        prompt_subquery = f"""Given the following database schema:
{schema}

Question: {question}

Write a SQL query that answers the question using subqueries where possible.
Return only the SQL query without any explanation or markdown."""

        system = "You are a helpful text-to-SQL assistant. Output only SQL."

        sql_join_raw = self.llm(prompt_join, system=system, temperature=0.0, n=1)
        sql_subq_raw = self.llm(prompt_subquery, system=system, temperature=0.0, n=1)

        sql_join = bridge.extract_sql(sql_join_raw)
        sql_subq = bridge.extract_sql(sql_subq_raw)

        result_join = self.execute(sql_join)
        result_subq = self.execute(sql_subq)

        join_non_empty = bool(result_join.get("ok")) and bool(result_join.get("rows"))
        subq_non_empty = bool(result_subq.get("ok")) and bool(result_subq.get("rows"))

        if join_non_empty:
            return sql_join
        if subq_non_empty:
            return sql_subq
        return sql_join