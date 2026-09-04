"""P2P2BMinimaxS2G6: two-stage harness where an initial LLM proposes a sketch that is refined into executable SQL."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: ask the LLM to produce a natural-language plan + intent summary
        plan_system = (
            "You are a Text-to-SQL planning assistant. Given a database schema and a "
            "natural language question, produce:\n"
            "  1. INTENT: a concise description of the desired result (one line).\n"
            "  2. PLAN: a numbered, step-by-step English plan describing which tables, "
            "joins, filters, aggregations and ordering are required to answer the question.\n"
            "Do NOT write SQL yet. Only produce the INTENT and PLAN sections."
        )
        plan_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Produce INTENT and PLAN now."
        )
        plan_resp = self.llm(plan_prompt, system=plan_system, temperature=0.0, n=1)
        plan_text = plan_resp if isinstance(plan_resp, str) else str(plan_resp)

        # Stage 2: ask the LLM to convert the plan into executable SQL
        sql_system = (
            "You are a Text-to-SQL generator. You will receive a database schema, a "
            "natural language question, and an INTENT/PLAN produced by a planner. "
            "Your job is to write a SINGLE executable SQL query that realises the plan. "
            "Return ONLY the SQL statement (no markdown fences, no commentary)."
        )
        sql_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Planner output:\n{plan_text}\n\n"
            "Now write the final SQL query."
        )
        sql_resp = self.llm(sql_prompt, system=sql_system, temperature=0.0, n=1)
        raw_sql = sql_resp if isinstance(sql_resp, str) else str(sql_resp)

        # Best-effort recovery if the model wraps the SQL in a code fence.
        final_sql = bridge.extract_sql(raw_sql) or raw_sql.strip()
        return final_sql