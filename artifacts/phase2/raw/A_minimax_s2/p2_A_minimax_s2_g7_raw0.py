"""Two-stage SQL synthesis where a planner first produces a query plan, then a coder generates SQL conditioned on that plan."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: produce a concise, schema-grounded query plan
        plan_system = (
            "You are a SQL planning assistant. Given a database schema and a natural "
            "language question, produce a short step-by-step plan describing which "
            "tables and columns to join, which filters to apply, and what the final "
            "SELECT should return. Output the plan text only, no SQL."
        )
        plan_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Plan:"
        )
        plan_text = self.llm(plan_prompt, system=plan_system, temperature=0.0, n=1)

        # Stage 2: generate SQL conditioned on the plan
        sql_system = (
            "You are an expert SQL generator. Given a schema, a natural language "
            "question, and a query plan, write a single correct SQLite-compatible "
            "SQL query that answers the question. Output only the SQL."
        )
        sql_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan_text}\n\n"
            "SQL:"
        )
        raw = self.llm(sql_prompt, system=sql_system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        # Validate by execution; if it fails, do one targeted repair pass that
        # still conditions on the plan to keep the intent stable.
        result = self.execute(sql)
        if not result.get("ok"):
            err = result.get("error", "")
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Plan:\n{plan_text}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Execution error:\n{err}\n\n"
                "Produce a corrected SQL query. SQL:"
            )
            repaired_raw = self.llm(
                repair_prompt,
                system="Fix the SQL so it executes correctly while following the plan.",
                temperature=0.0,
                n=1,
            )
            sql = bridge.extract_sql(repaired_raw)

        return sql