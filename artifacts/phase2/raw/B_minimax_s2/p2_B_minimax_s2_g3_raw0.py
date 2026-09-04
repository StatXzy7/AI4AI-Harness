# Docstring: Two-stage harness where a planner LLM drafts a skeleton and the main LLM fills in the full SQL.
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G3(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: planner produces a skeleton of the query (FROM/JOIN/aliases and intent)
        plan_prompt = (
            "You are a SQL planner. Given the schema and a natural language question, "
            "produce a short JSON-like plan listing: needed_tables, joins (with conditions), "
            "filters_in_intent, grouping_in_intent, metrics_in_intent. Do not write the full SQL yet.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Plan:"
        )
        plan_text = self.llm(plan_prompt, system="You are a precise SQL planner.", temperature=0.0, n=1)

        # Stage 2: main LLM consumes the plan and writes the final SQL
        main_prompt = (
            "You are an expert SQL writer. Using the provided schema and the planner's notes, "
            "write a single SQLite-compatible SQL query that answers the question. "
            "Return ONLY the SQL, with no markdown, no commentary, no explanation.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Planner notes:\n{plan_text}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        raw = self.llm(main_prompt, system="You write correct SQLite SQL.", temperature=0.0, n=1)

        sql = bridge.extract_sql(raw)

        # Light sanity: strip stray trailing semicolons/spaces
        if sql.endswith(";"):
            sql = sql[:-1].rstrip()

        return sql