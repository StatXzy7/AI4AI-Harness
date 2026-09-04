"""A two-stage plan-then-SQL harness with execution-guided repair for weak Text-to-SQL models."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G2(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        # Stage 1: Generate a concise solution plan to ground SQL generation.
        plan_prompt = f"""You are given a database schema and a question.
Produce a concise step-by-step plan to answer the question using SQL.
Identify relevant tables, columns, joins, filters, aggregations, and grouping.
Do not write SQL yet.

Database schema:
{schema}

Question:
{question}

Plan:
"""
        plan_response = self.llm(
            plan_prompt,
            system="You are a world-class SQL planning assistant. Think carefully before generating SQL.",
            temperature=0.0,
            n=1,
        )
        plan = (plan_response or "").strip()
        if not plan:
            plan = "No explicit plan generated."

        # Stage 2: Convert the plan into a SQL query.
        sql_prompt = f"""You are given a database schema, a question, and a solution plan.
Write a single valid SQL query that answers the question.
Follow the plan exactly. Output only SQL.

Database schema:
{schema}

Question:
{question}

Plan:
{plan}

SQL:
"""
        sql_response = self.llm(
            sql_prompt,
            system="You are a precise SQL generator. Return only SQL.",
            temperature=0.0,
            n=1,
        )
        sql = bridge.extract_sql(sql_response) or (sql_response or "").strip()

        # Stage 3: Execution-guided repair loop.
        max_repairs = 3
        for _ in range(max_repairs):
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                return sql

            error = result.get("error") or "Unknown execution error."

            repair_prompt = f"""The following SQL query for the question failed.
Please fix it so that it executes successfully and answers the question.

Database schema:
{schema}

Question:
{question}

Plan:
{plan}

Previous SQL:
{sql}

Error:
{error}

Output only the corrected SQL.
"""
            repair_response = self.llm(
                repair_prompt,
                system="You are a SQL debugger. Fix the query and return only SQL.",
                temperature=0.0,
                n=1,
            )
            sql = bridge.extract_sql(repair_response) or (repair_response or "").strip()

        return sql