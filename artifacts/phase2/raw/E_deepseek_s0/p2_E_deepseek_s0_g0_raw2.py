"""A plan-then-execute harness that first builds a short SQL plan, generates a query from that plan, and repairs it with execution feedback."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G0(SQLHarness):
    MAX_REPAIRS = 3

    def solve(self, question: str) -> str:
        plan = self._plan(question)
        sql = self._generate_sql(question, plan)

        for _ in range(self.MAX_REPAIRS):
            result = self.execute(sql)
            if result.get("ok") and result.get("rows"):
                return sql

            feedback = self._build_feedback(result)
            sql = self._repair_sql(question, plan, sql, feedback)

        return sql

    def _call_llm(self, prompt: str, system: str = "") -> str:
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        if isinstance(raw, dict):
            raw = raw.get("text") or raw.get("content") or raw.get("completion") or ""
        return str(raw)

    def _plan(self, question: str) -> str:
        prompt = (
            "You are analyzing a text-to-SQL problem.\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a concise step-by-step plan for the SQL query. "
            "Identify the tables, columns, joins, filters, grouping, and ordering needed. "
            "Do not write SQL yet."
        )
        return self._call_llm(
            prompt,
            system="You are a careful SQL planner.",
        )

    def _generate_sql(self, question: str, plan: str) -> str:
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan}\n\n"
            "Write a single SQL query that follows the plan and answers the question. "
            "Return only the SQL query, no explanation."
        )
        raw = self._call_llm(
            prompt,
            system="You are a precise text-to-SQL assistant.",
        )
        return bridge.extract_sql(raw) or raw.strip()

    def _repair_sql(self, question: str, plan: str, previous_sql: str, feedback: str) -> str:
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Plan:\n{plan}\n\n"
            f"Previous SQL:\n{previous_sql}\n\n"
            f"Execution feedback:\n{feedback}\n\n"
            "Rewrite the SQL to fix the problem. Return only the corrected SQL query."
        )
        raw = self._call_llm(
            prompt,
            system="You are a precise text-to-SQL repair assistant.",
        )
        extracted = bridge.extract_sql(raw) or raw.strip()
        return extracted if extracted else previous_sql

    def _build_feedback(self, result: dict) -> str:
        if not result.get("ok"):
            return f"Error: {result.get('error', 'unknown execution error')}"
        if not result.get("rows"):
            return (
                "The query executed successfully but returned no rows. "
                "If the answer should not be empty, adjust filters, joins, or table choices."
            )
        return "The query executed successfully."