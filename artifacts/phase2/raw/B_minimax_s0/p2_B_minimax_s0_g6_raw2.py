# Two-stage Text-to-SQL: a planning stage extracts relevant tables/columns, then a synthesis stage generates the final SQL using the focused plan.
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS0G6(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        plan_prompt = (
            "You are a database planner. Given the user question and the database schema, "
            "identify ONLY the tables and columns that are relevant to answering the question. "
            "Be concise. Output a short bulleted plan.\n\n"
            f"SCHEMA:\n{schema}\n\n"
            f"QUESTION: {question}\n\n"
            "RELEVANT TABLES AND COLUMNS (bullet list):"
        )
        plan = self.llm(plan_prompt, system="", temperature=0.0, n=1).strip()

        synth_prompt = (
            "You are a SQL generator. Given the user question, the full schema, and a focused "
            "plan of relevant tables/columns, write a single SQLite-compatible SQL query that "
            "answers the question. Use ONLY tables/columns listed in the plan. Output only the SQL.\n\n"
            f"SCHEMA:\n{schema}\n\n"
            f"PLAN:\n{plan}\n\n"
            f"QUESTION: {question}\n\n"
            "SQL:"
        )
        raw = self.llm(synth_prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        ok_info = self.execute(sql)
        if not ok_info.get("ok", False):
            err = ok_info.get("error", "unknown error")
            repair_prompt = (
                "The following SQL failed when executed against the database. "
                "Fix the error and return a corrected SQLite-compatible SQL query. "
                "Output only the SQL.\n\n"
                f"SCHEMA:\n{schema}\n\n"
                f"PLAN:\n{plan}\n\n"
                f"QUESTION: {question}\n\n"
                f"FAILED SQL:\n{sql}\n\n"
                f"ERROR:\n{err}\n\n"
                "CORRECTED SQL:"
            )
            repaired_raw = self.llm(repair_prompt, system="", temperature=0.0, n=1)
            repaired_sql = bridge.extract_sql(repaired_raw)
            if repaired_sql:
                sql = repaired_sql

        return sql