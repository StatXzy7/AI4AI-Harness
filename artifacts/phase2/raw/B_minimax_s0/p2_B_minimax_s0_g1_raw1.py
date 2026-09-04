"""Two-stage Text-to-SQL: first generate a structured query plan, then synthesize SQL from it."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        # ---- Stage 1: produce a structured natural-language plan ----
        plan_system = (
            "You are a query planner. Given a database schema and a natural language "
            "question, produce a concise step-by-step plan in plain English. "
            "Identify which tables and columns are needed, what filters to apply, "
            "what aggregations or joins are required, and the expected output shape. "
            "Do not write SQL. Output only the plan."
        )
        plan_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Plan:"
        )
        plan_text = self.llm(plan_prompt, system=plan_system, temperature=0.0, n=1).strip()
        if not plan_text:
            plan_text = "Use the relevant tables to answer the question."

        # ---- Stage 2: synthesize SQL from schema + question + plan ----
        sql_system = (
            "You are an expert SQL writer. Given a database schema, a natural language "
            "question, and a query plan, write a single correct SQLite-compatible SQL "
            "statement that answers the question. Follow the plan exactly. "
            "Output only the SQL statement, no commentary, no markdown."
        )
        sql_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Query Plan:\n{plan_text}\n\n"
            "SQL:"
        )
        raw_sql = self.llm(sql_prompt, system=sql_system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw_sql)

        if not sql:
            # Fallback: try to use anything that looks SQL-ish from the raw output.
            return raw_sql.strip()

        return sql