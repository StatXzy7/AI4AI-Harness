"""Two-stage SQL generation: first plan the query skeleton, then synthesize final SQL."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G1(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: produce a planning skeleton (tables/columns/joins/filters).
        plan_system = (
            "You are a SQL planning assistant. Given a natural language question and a "
            "database schema, produce a concise plan that identifies the relevant tables, "
            "columns, joins, filters, and aggregations needed. Do NOT write SQL."
        )
        plan_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Provide a step-by-step plan listing tables, joins, columns, where-clauses, "
            "and any aggregations or ordering."
        )
        plan = self.llm(plan_prompt, system=plan_system, temperature=0.0, n=1).strip()

        # Stage 2: synthesize the final SQL, conditioned on the plan.
        sql_system = (
            "You are a precise SQL generator. Given a schema, a planning outline, and a "
            "question, write a single correct SQL query that answers it. Output only SQL."
        )
        sql_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Plan:\n{plan}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        raw = self.llm(sql_prompt, system=sql_system, temperature=0.0, n=1)
        final_sql = bridge.extract_sql(raw)
        if not final_sql:
            # Fallback: try a direct generation if extraction returned nothing.
            raw = self.llm(
                f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nSQL:",
                system="You are a precise SQL generator. Output only SQL.",
                temperature=0.0,
                n=1,
            )
            final_sql = bridge.extract_sql(raw)

        return final_sql or ""