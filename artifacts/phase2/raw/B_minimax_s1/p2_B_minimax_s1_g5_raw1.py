"""Two-stage pipeline: first stage drafts a skeletal plan with referenced tables/columns, second stage produces the final SQL conditioned on that plan."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS1G5(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: extract a compact schema-grounded plan (relevant tables/columns + intent)
        plan_prompt = (
            "Given the database schema and the user's question, produce a brief plan.\n"
            "The plan must list the tables and columns you will use, the joins needed, "
            "any filters, and the expected output columns.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Plan:"
        )
        plan = self.llm(plan_prompt, system="You are a careful Text-to-SQL planner.", temperature=0.0, n=1).strip()

        # Stage 2: generate the final SQL conditioned on the plan, grounded again in the schema
        sql_prompt = (
            "You are a Text-to-SQL generator. Use the provided plan as your blueprint and "
            "the schema as the source of truth for table/column names.\n"
            "Return exactly one SQL statement wrapped in