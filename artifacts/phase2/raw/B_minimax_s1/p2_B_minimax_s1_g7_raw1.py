"""Two-stage harness: first LLM drafts a plan, second LLM converts the plan into SQL with schema context, then we execute and repair on failure."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS1G7(SQLHarness):
    """Two-stage Text-to-SQL: plan generation followed by plan-to-SQL synthesis, with execution repair fallback."""

    def solve(self, question: str) -> str:
        schema = self.schema
        # Stage 1: draft a textual plan describing tables, joins, filters, and aggregations.
        plan_prompt = (
            "You are planning a SQL query. Given the database schema and the user's question, "
            "produce a concise step-by-step plan listing the relevant tables, required joins, "
            "filter conditions, aggregations, and ordering. Do NOT write SQL yet.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Plan:"
        )
        plan_text = self.llm(plan_prompt, system="", temperature=0.0, n=1)
        plan_text = (plan_text or "").strip()

        # Stage 2: convert the plan into executable SQL using schema + plan as context.
        sql_prompt = (
            "You are generating a SQLite-compatible SQL query. Use the schema and the plan "
            "below to write a single SQL statement that answers the question. "
            "Return ONLY the SQL statement with no commentary or markdown fences.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Plan:\n{plan_text}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        raw = self.llm(sql_prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        # Repair loop: if SQL fails to execute, feed the error back for a single regeneration.
        if sql:
            result = self.execute(sql)
            if not result.get("ok", False):
                error_msg = result.get("error", "unknown error")
                repair_prompt = (
                    "The following SQL query failed to execute. Diagnose the issue using the "
                    "error message and the schema, then return a corrected SQL statement. "
                    "Return ONLY the corrected SQL with no commentary.\n\n"
                    f"Schema:\n{schema}\n\n"
                    f"Plan:\n{plan_text}\n\n"
                    f"Question: {question}\n\n"
                    f"Original SQL:\n{sql}\n\n"
                    f"Error:\n{error_msg}\n\n"
                    "Corrected SQL:"
                )
                repaired_raw = self.llm(repair_prompt, system="", temperature=0.0, n=1)
                repaired_sql = bridge.extract_sql(repaired_raw)
                if repaired_sql:
                    sql = repaired_sql

        return sql if sql else ""