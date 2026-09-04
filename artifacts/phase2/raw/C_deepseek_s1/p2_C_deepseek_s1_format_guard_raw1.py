"""P2P2C DeepSeek S1 format-guard harness that plans, generates fenced SQL, and iteratively corrects format and execution errors while emphasizing schema fidelity."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS1FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # ----- Stage 1: Plan -----
        plan_system = (
            "You are a SQL query planner. Given a database schema and a natural language question, "
            "produce a concise, step-by-step plan for constructing the correct SQL query. "
            "Identify relevant tables, columns, joins, filters, groupings, and aggregations. "
            "Use only the provided schema. Do not write the SQL yet."
        )
        plan_prompt = f"Schema:\n{self.schema}\n\nQuestion:\n{question}\n\nPlan:"
        plan = self.llm(plan_prompt, system=plan_system, temperature=0.0, n=1)

        # ----- Stage 2: Prompt for fenced SQL generation -----
        sql_system = (
            "You are a precise text-to-SQL generator.\n"
            "Output requirements:\n"
            "1. Use only the provided schema.\n"
            "2. Return exactly one SQL statement inside a