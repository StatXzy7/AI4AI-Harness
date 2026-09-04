"""Defines a two-phase plan-then-generate SQL harness with execution-guided self-repair."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G1(SQLHarness):
    """A harness that plans, generates, executes, and repairs SQL iteratively."""

    def solve(self, question: str) -> str:
        plan = self._generate_plan(question)
        sql = self._generate_sql(question, plan)
        sql = bridge.extract_sql(sql) or sql.strip()

        for _ in range(3):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error") or "Unknown error"
            repaired = self._repair_sql(question, plan, sql, error)
            extracted = bridge.extract_sql(repaired)

            if extracted:
                sql = extracted.strip()
            elif repaired.strip():
                sql = repaired.strip()
            # If no useful repair output is produced, keep the previous SQL
            # and let the next execute/repair cycle handle it.
        return sql

    def _generate_plan(self, question: str) -> str:
        prompt = (
            "You are helping to write SQL for the following SQLite schema.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Before writing SQL, produce a concise execution plan. "
            "Identify relevant tables, columns, joins, filters, groupings, and aggregations. "
            "Do not write the final SQL yet."
        )
        return self.llm(
            prompt,
            system="You are a careful database query planner.",
            temperature=0.0,
            n=1,
        )

    def _generate_sql(self, question: str, plan: str) -> str:
        prompt = (
            "You are writing SQLite SQL for the following schema.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Execution plan:\n{plan}\n\n"
            "Write a single SQL SELECT statement that answers the question. "
            "Output only the SQL."
        )
        return self.llm(
            prompt,
            system="You are an expert SQLite SQL engineer.",
            temperature=0.0,
            n=1,
        )

    def _repair_sql(self, question: str, plan: str, previous_sql: str, error: str) -> str:
        prompt = (
            "You are debugging SQLite SQL for the following schema.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Execution plan:\n{plan}\n\n"
            f"Previous SQL:\n{previous_sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Write a corrected SQL SELECT statement that answers the question. "
            "Output only the SQL."
        )
        return self.llm(
            prompt,
            system="You are an expert SQLite SQL debugger.",
            temperature=0.0,
            n=1,
        )