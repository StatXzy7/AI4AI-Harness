# Harness that runs a single plan-then-SQL generation: first stage drafts a query plan/intent, second stage produces SQL conditioned on it.
"""Two-stage harness: stage 1 drafts a textual plan/intent, stage 2 generates SQL conditioned on the plan."""
# MECHANISM: twostage

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: ask the LLM to produce a concise, schema-aware plan/intent.
        # This step is a real control-flow addition (not just prompt decoration) because its
        # output is fed verbatim into the stage-2 prompt, changing the conditioning context.
        plan_system = (
            "You are a query planner for a text-to-SQL system. Read the schema and the user's "
            "question, then produce a short, focused plan describing which tables/columns are "
            "involved, the relevant join conditions, any filters/aggregations, and the expected "
            "shape of the result. Do NOT write SQL. Output only the plan."
        )
        plan_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Plan (no SQL):"
        )
        plan_text = self.llm(plan_prompt, system=plan_system, temperature=0.0, n=1).strip()

        # Stage 2: generate SQL conditioned on both the schema and the drafted plan.
        sql_system = (
            "You are a careful text-to-SQL generator. Follow the provided plan exactly. "
            "Output only a single SQL query (no prose, no markdown)."
        )
        sql_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan_text}\n\n"
            "SQL:"
        )
        raw_sql = self.llm(sql_prompt, system=sql_system, temperature=0.0, n=1)
        final_sql = bridge.extract_sql(raw_sql)

        # Fallback: if extraction yielded nothing (rare), retry stage 2 once without the plan.
        if not final_sql:
            fallback_prompt = (
                f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nSQL:"
            )
            raw_sql = self.llm(fallback_prompt, system=sql_system, temperature=0.0, n=1)
            final_sql = bridge.extract_sql(raw_sql)

        return final_sql