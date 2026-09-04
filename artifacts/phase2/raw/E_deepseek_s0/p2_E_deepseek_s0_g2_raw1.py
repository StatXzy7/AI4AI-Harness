"""This harness plans the query, generates SQL from the plan, and repairs it using execution feedback."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G2(SQLHarness):
    MAX_REPAIR_ATTEMPTS = 3

    def solve(self, question: str) -> str:
        plan = self._create_plan(question)
        sql = self._generate_sql(question, plan)

        # Fallback: try generation once more with a slightly higher temperature
        if not sql:
            sql = self._generate_sql(question, plan, temperature=0.1)

        for attempt in range(self.MAX_REPAIR_ATTEMPTS):
            result = self._safe_execute(sql)
            if result["ok"]:
                return sql

            previous_sql = sql
            sql = self._repair_sql(
                question=question,
                plan=plan,
                previous_sql=previous_sql,
                error=result["error"] or "Unknown error",
                attempt=attempt,
            )
            if not sql:
                sql = previous_sql

        return sql

    def _safe_execute(self, sql: str) -> dict:
        if not sql:
            return {"ok": False, "rows": [], "error": "Empty SQL string"}
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    def _create_plan(self, question: str) -> str:
        system = (
            "You are a SQL query planner. You break down a natural-language question "
            "into the exact tables, columns, join conditions, filters, and any tricky "
            "or ambiguous terms before SQL is written."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Produce a short planning note that identifies:\n"
            "1. the tables and columns needed,\n"
            "2. join conditions if multiple tables are involved,\n"
            "3. filter conditions and any specific values mentioned by the user,\n"
            "4. any ambiguous terms and how you will resolve them.\n"
            "Do not generate SQL in this step."
        )
        return self.llm(prompt, system=system, temperature=0.0, n=1).strip()

    def _generate_sql(self, question: str, plan: str, temperature: float = 0.0) -> str:
        system = (
            "You are a SQL writer for a read-only analytics database. "
            "Write only a single valid SQL SELECT statement, with no explanation."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Planning notes:\n{plan}\n\n"
            "Use the plan to write a correct SQL SELECT statement. "
            "Output only the SQL statement."
        )
        raw = self.llm(prompt, system=system, temperature=temperature, n=1)
        return bridge.extract_sql(raw) or ""

    def _repair_sql(self, question: str, plan: str, previous_sql: str, error: str, attempt: int) -> str:
        system = (
            "You are a SQL repair agent. You fix SQL statements based on database error messages."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Planning notes:\n{plan}\n\n"
            f"Previous SQL:\n{previous_sql}\n\n"
            f"The execution failed with this error:\n{error}\n\n"
            f"Repair attempt {attempt + 1}. Produce a corrected SQL SELECT statement. "
            "Output only the corrected SQL statement."
        )
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw) or ""
        return sql if sql else previous_sql