"""Wraps the weak solver with a two-stage generation: plan then SQL, with execution-based repair fallback."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        # Stage 1: generate a brief plan (which tables, columns, filters, joins, aggregations).
        plan_prompt = (
            "You are planning a SQL query.\n"
            "Given the database schema and a question, produce a SHORT step-by-step plan listing:\n"
            "  - tables involved\n"
            "  - key columns and join keys\n"
            "  - relevant filters and aggregations\n"
            "Do NOT write SQL. Do not include commentary outside the plan.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Plan:"
        )
        plan_text = self.llm(plan_prompt, system="You plan SQL.", temperature=0.0, n=1).strip()

        # Stage 2: generate SQL conditioned on the plan.
        sql_prompt = (
            "Write a single SQLite-compatible SQL query that answers the question, "
            "following the provided plan.\n"
            "Output ONLY the SQL. No markdown, no explanation.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Plan:\n{plan_text}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        sql_text = self.llm(sql_prompt, system="You write SQL.", temperature=0.0, n=1)

        sql = bridge.extract_sql(sql_text) or sql_text.strip()
        if not sql:
            return ""

        # Repair loop: execute; if it fails, feed the error back for one regeneration
        # conditioned on the same plan.
        last_err = ""
        for attempt in range(2):
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            last_err = (result.get("error") or "unknown error").strip()
            if attempt == 1:
                break

            repair_prompt = (
                "Fix the SQL so it executes successfully. The previous attempt raised an error.\n"
                "Output ONLY the corrected SQL. No markdown, no explanation.\n\n"
                f"Schema:\n{schema}\n\n"
                f"Plan:\n{plan_text}\n\n"
                f"Question: {question}\n\n"
                f"Failed SQL:\n{sql}\n\n"
                f"Error:\n{last_err}\n\n"
                "Corrected SQL:"
            )
            sql_repair = self.llm(repair_prompt, system="You repair SQL.", temperature=0.0, n=1)
            new_sql = bridge.extract_sql(sql_repair) or sql_repair.strip()
            if not new_sql or new_sql == sql:
                break
            sql = new_sql

        return sql