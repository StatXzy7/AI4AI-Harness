"""Two-stage Text-to-SQL: first generate a structured plan, then generate SQL conditioned on that plan."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        # --- Stage 1: produce a plan/blueprint of which tables/columns/joins/conditions are needed ---
        plan_system = (
            "You are a SQL planning assistant. Given a database schema and a natural "
            "language question, produce a concise plan describing which tables and columns "
            "are needed, how they are joined, and which filters/aggregations to apply. "
            "Do NOT write the final SQL. Output only the plan as a short bulleted list."
        )
        plan_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Plan:"
        )
        plan_text = self.llm(plan_prompt, system=plan_system, temperature=0.0, n=1)
        plan_text = (plan_text or "").strip()

        # --- Stage 2: generate SQL conditioned on the plan, using a fresh prompt context ---
        sql_system = (
            "You are a Text-to-SQL generator. Given a schema, a natural language question, "
            "and a plan, produce a single executable SQLite SQL query that answers the question. "
            "Use only tables/columns mentioned in the plan. Output ONLY the SQL."
        )
        sql_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan_text}\n\n"
            "SQL:"
        )
        sql_text = self.llm(sql_prompt, system=sql_system, temperature=0.0, n=1)

        final_sql = bridge.extract_sql(sql_text)

        # Light safety net: if extraction failed, fall back to a raw single-call generation.
        if not final_sql or not final_sql.strip():
            fallback = self.llm(
                f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nSQL:",
                system="You are a Text-to-SQL generator. Output only SQL.",
                temperature=0.0,
                n=1,
            )
            final_sql = bridge.extract_sql(fallback) or ""

        return final_sql or ""