"""Two-stage Text-to-SQL: a first LLM drafts a skeleton/plan, then a second LLM generates the final SQL conditioned on that plan."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS1G1(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: produce a concise plan/sketch describing which tables/columns/joins/filters
        # the SQL should use. This is consumed verbatim by stage 2.
        planning_prompt = (
            "You are an expert database analyst.\n"
            "Given the database schema below and a natural language question, "
            "produce a short PLAN (not SQL) that identifies:\n"
            "  - which tables are needed,\n"
            "  - which columns to select,\n"
            "  - join keys,\n"
            "  - filter / WHERE conditions (with values when known),\n"
            "  - any aggregation or grouping,\n"
            "  - the expected shape of the output.\n"
            "Keep the plan terse and concrete. Do NOT write SQL.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            "PLAN:"
        )

        plan = self.llm(planning_prompt, system="", temperature=0.0, n=1).strip()

        # Stage 2: condition the SQL generation on the plan from stage 1.
        sql_prompt = (
            "You are an expert Text-to-SQL writer.\n"
            "Write a single SQLite-compatible SQL query that answers the QUESTION.\n"
            "Follow the PLAN exactly. Use only tables/columns that appear in the SCHEMA.\n"
            "Return ONLY the SQL inside a