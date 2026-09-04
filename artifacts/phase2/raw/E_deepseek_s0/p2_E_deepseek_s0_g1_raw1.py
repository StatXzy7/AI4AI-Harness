"""Harness that generates a plan, uses it to produce SQL, then iteratively repairs failed queries using execution feedback."""
from ..harness_base import SQLHarness
from .. import bridge

class P2P2EDeepseekS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Generate a natural language plan for the SQL query
        plan_prompt = f"""Given the following database schema:
{self.schema}

Question: {question}

Provide a step-by-step plan for writing a SQL query to answer the question. Describe the tables, columns, joins, filters, aggregations, and any other relevant details. Do not write the actual SQL query yet."""

        plan_response = self.llm(plan_prompt, system="You are an expert SQL query planner.", temperature=0.2, n=1).strip()
        if not plan_response:
            plan_response = "No plan generated."

        # Step 2: Generate SQL using the plan
        sql_prompt = f"""Given the database schema:
{self.schema}

Question: {question}

Plan:
{plan_response}

Now write the SQL query that implements this plan. Output only the SQL query, nothing else."""

        sql_response = self.llm(sql_prompt, system="You are an expert SQL writer.", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_response)

        # Fallback: if no SQL generated, try direct generation without plan
        if not sql:
            direct_prompt = f"""Given schema:
{self.schema}

Question: {question}

Write a SQL query for SQLite. Output only the SQL query."""
            sql_response = self.llm(direct_prompt, system="You are a SQL expert.", temperature=0.0, n=1)
            sql = bridge.extract_sql(sql_response)
        if not sql:
            return ""

        # Execute initial SQL
        result = self.execute(sql)
        if result["ok"]:
            return sql

        # Repair loop with execution feedback
        max_retries = 3
        prev_sql = sql
        for attempt in range(1, max_retries + 1):
            error_msg = result.get("error", "Unknown error")
            repair_prompt = f"""The following SQL query for SQLite produced an error.

Database schema:
{self.schema}

Question: {question}

Previous SQL:
{prev_sql}

Error:
{error_msg}

Please fix the SQL query. Output only the corrected SQL query."""
            repair_response = self.llm(repair_prompt, system="You are an expert SQL repair assistant.", temperature=0.0, n=1)
            repaired_sql = bridge.extract_sql(repair_response)
            if not repaired_sql:
                break
            result = self.execute(repaired_sql)
            if result["ok"]:
                return repaired_sql
            prev_sql = repaired_sql

        # If all retries fail, return the last attempted SQL
        return prev_sql