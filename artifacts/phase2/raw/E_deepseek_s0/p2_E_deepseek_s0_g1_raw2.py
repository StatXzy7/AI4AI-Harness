"""Uses a plan-then-generate-then-verify control flow to iteratively repair Text-to-SQL queries with execution feedback."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G1(SQLHarness):
    MAX_REPAIRS = 2

    def solve(self, question: str) -> str:
        plan = self._generate_plan(question)
        sql = self._generate_sql(question, plan)
        if not sql:
            return ""

        for _ in range(self.MAX_REPAIRS):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            repair_prompt = self._build_repair_prompt(
                question, plan, sql, result.get("error", "unknown execution error")
            )
            raw = self.llm(
                repair_prompt,
                system="You are a SQL repair expert. Output only a corrected SQL query.",
                temperature=0.0,
                n=1,
            )
            candidate = bridge.extract_sql(raw) or ""
            if not candidate:
                return sql
            sql = candidate

        result = self.execute(sql)
        if result.get("ok"):
            return sql
        return sql

    def _generate_plan(self, question: str) -> str:
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Before writing SQL, write a concise step-by-step plan for solving this question. "
            "Identify relevant tables, columns, joins, filters, groupings, and aggregation logic. "
            "Do not output SQL in this step."
        )
        raw = self.llm(
            prompt,
            system="You are a careful SQL planning assistant. Use only the provided schema.",
            temperature=0.0,
            n=1,
        )
        return raw.strip()

    def _generate_sql(self, question: str, plan: str) -> str:
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Planning notes:\n"
            f"{plan}\n\n"
            "Write a single SQL query that follows the plan and answers the question. Output only the SQL query."
        )
        raw = self.llm(
            prompt,
            system="You are a precise SQL generator. Use only the provided schema.",
            temperature=0.0,
            n=1,
        )
        return bridge.extract_sql(raw) or ""

    def _build_repair_prompt(
        self, question: str, plan: str, previous_sql: str, error: str
    ) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Planning notes:\n"
            f"{plan}\n\n"
            "Previous SQL query:\n"
            f"{previous_sql}\n\n"
            "Execution error:\n"
            f"{error}\n\n"
            "Write a corrected single SQL query that fixes the error and still answers the question. "
            "Double-check column/table names, join conditions, grouping, and aggregation. Output only the SQL query."
        )