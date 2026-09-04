"""Two-stage harness: first stage produces a schema-grounded sketch, second stage expands it into SQL with execution-based repair fallback."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G5(SQLHarness):
    def solve(self, question: str) -> str:
        # ---------- Stage 1: identify relevant tables/columns and intent ----------
        stage1_system = (
            "You are a SQL planning assistant. Given a database schema and a natural "
            "language question, identify only the relevant tables, columns, joins, and "
            "filters needed. Output a concise plan in plain text. Do NOT write SQL yet."
        )
        stage1_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Plan (tables, columns, joins, conditions, expected output):"
        )
        plan = self.llm(stage1_prompt, system=stage1_system, temperature=0.0, n=1).strip()

        # ---------- Stage 2: expand the plan into a full SQL query ----------
        stage2_system = (
            "You are an expert SQLite SQL generator. Given a schema, a question, and "
            "a plan, produce a single executable SQL statement. Output ONLY the SQL."
        )
        stage2_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan}\n\n"
            "SQL:"
        )
        raw = self.llm(stage2_prompt, system=stage2_system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        # ---------- Inline repair pass: feed execution errors back once ----------
        result = self.execute(sql)
        if not result.get("ok"):
            err = result.get("error", "unknown error")
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Plan:\n{plan}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Execution error:\n{err}\n\n"
                "Produce a corrected SQL statement. Output ONLY the SQL."
            )
            raw2 = self.llm(repair_prompt, system=stage2_system, temperature=0.0, n=1)
            sql2 = bridge.extract_sql(raw2)
            if sql2:
                sql = sql2

        return sql