"""Two-stage generation where a planner extracts key entities/columns before SQL synthesis, combined with execution-based repair."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS2G1(SQLHarness):
    def solve(self, question: str) -> str:
        # ---- Stage 1: Planner ----
        # Extract a compact plan: relevant tables, columns, joins, and conditions.
        plan_prompt = (
            "You are a planning assistant for a Text-to-SQL system.\n"
            "Given the database schema and a natural language question, "
            "produce a concise PLAN that lists:\n"
            "  - Relevant tables\n"
            "  - Relevant columns (and which table each lives in)\n"
            "  - Any required JOIN conditions\n"
            "  - Any WHERE / HAVING / GROUP BY / ORDER BY conditions\n"
            "  - Aggregation needs (SUM, COUNT, AVG, MAX, MIN)\n"
            "Do NOT write SQL. Just produce the plan.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "PLAN:"
        )
        plan_text = self.llm(plan_prompt, system="", temperature=0.0, n=1)
        plan = (plan_text or "").strip()

        # ---- Stage 2: SQL synthesis conditioned on the plan ----
        sql_prompt = (
            "You are a Text-to-SQL system.\n"
            "Use the provided PLAN to write a SINGLE SQL query that answers the question.\n"
            "Follow the plan faithfully. Use only tables/columns that appear in the schema.\n"
            "Return ONLY the SQL query (no explanation, no markdown).\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Plan:\n{plan}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        sql_text = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(sql_text or "")

        # ---- Lightweight repair: execution-guided re-prompt on failure ----
        if sql:
            result = self.execute(sql)
            if not result.get("ok"):
                err = result.get("error", "unknown error")
                repair_prompt = (
                    "The following SQL failed to execute. Diagnose the error and produce a "
                    "corrected SQL query. Return ONLY the corrected SQL.\n\n"
                    f"Schema:\n{self.schema}\n\n"
                    f"Plan:\n{plan}\n\n"
                    f"Question: {question}\n\n"
                    f"Failed SQL:\n{sql}\n\n"
                    f"Error:\n{err}\n\n"
                    "Corrected SQL:"
                )
                fixed_text = self.llm(repair_prompt, system="", temperature=0.0, n=1)
                fixed_sql = bridge.extract_sql(fixed_text or "")
                if fixed_sql:
                    sql = fixed_sql

        return sql