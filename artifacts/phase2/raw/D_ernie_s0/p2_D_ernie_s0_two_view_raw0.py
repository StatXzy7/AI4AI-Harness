"""Generates two independent SQL formulations (join-based and subquery-based) from the question, executes both, and returns the non-empty result."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS0TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        # Prompt the LLM to produce two distinct SQL formulations
        prompt = f"""Given the following database schema and question, write TWO different SQL queries that answer the question.

Schema:
{self.schema}

Question: {question}

Provide two formulations:
1. A join-based SQL query
2. A subquery-based SQL query

Format your response exactly as:
JOIN_SQL: <first query here>
SUBQUERY_SQL: <second query here>

Only output the two labeled queries, nothing else."""

        response = self.llm(prompt, system="", temperature=0.0, n=1)

        # Parse the two labeled queries from the response
        join_sql = None
        subquery_sql = None
        for line in response.strip().split('\n'):
            line = line.strip()
            if line.startswith("JOIN_SQL:"):
                join_sql = line[len("JOIN_SQL:"):].strip()
            elif line.startswith("SUBQUERY_SQL:"):
                subquery_sql = line[len("SUBQUERY_SQL:"):].strip()

        # Fallback to bridge extraction if parsing didn't find both
        if join_sql is None:
            join_sql = bridge.extract_sql(response)
        if subquery_sql is None:
            subquery_sql = bridge.extract_sql(response)

        # Execute the join-based formulation
        join_result = {"ok": False, "rows": [], "error": "no sql"}
        if join_sql:
            join_result = self.execute(join_sql)

        # Execute the subquery-based formulation
        subquery_result = {"ok": False, "rows": [], "error": "no sql"}
        if subquery_sql:
            subquery_result = self.execute(subquery_sql)

        # Return the non-empty result; if both are non-empty, return the first (join-based)
        if join_result["ok"] and join_result["rows"]:
            return join_sql
        elif subquery_result["ok"] and subquery_result["rows"]:
            return subquery_sql
        else:
            # Both empty or errored: return the join-based query if available, else subquery
            return join_sql if join_sql else subquery_sql