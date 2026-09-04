"""An execution-feedback harness that plans, generates, executes, and repairs SQL for Text-to-SQL."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        max_attempts = 3

        def ask(prompt: str, system: str = "") -> str:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
            if isinstance(response, list):
                response = response[0] if response else ""
            return str(response)

        plan = self._make_plan(question, ask)
        raw_sql = self._generate_sql(question, plan, ask)
        last_sql = bridge.extract_sql(raw_sql) or raw_sql.strip()

        for attempt in range(max_attempts):
            if not last_sql:
                raw_sql = self._generate_sql(
                    question,
                    plan,
                    ask,
                    note="Previous response contained no SQL.",
                )
                last_sql = bridge.extract_sql(raw_sql) or raw_sql.strip()
                if not last_sql:
                    break
                continue

            result = self.execute(last_sql)

            if result.get("ok"):
                return last_sql

            error = result.get("error", "unknown execution error")
            plan = self._revise_plan(question, plan, last_sql, error, ask)
            raw_sql = self._generate_sql(
                question,
                plan,
                ask,
                error=error,
                previous_sql=last_sql,
            )

            extracted = bridge.extract_sql(raw_sql)
            if extracted:
                last_sql = extracted
            elif raw_sql.strip():
                last_sql = raw_sql.strip()
            # Otherwise keep previous SQL and allow loop to run its course.

        return last_sql

    def _make_plan(self, question: str, ask) -> str:
        system = "You are a senior SQL query planner. Respond only with a concise execution plan."
        prompt = f"""Database schema:
{self.schema}

Question:
{question}

Produce a short query plan that identifies:
- relevant tables
- required columns
- join conditions
- filter conditions

Do not write SQL."""
        return ask(prompt, system=system)

    def _revise_plan(self, question: str, plan: str, previous_sql: str, error: str, ask) -> str:
        system = "You are a senior SQL query debugger. Update the plan only."
        prompt = f"""Database schema:
{self.schema}

Question:
{question}

Previous plan:
{plan}

Previous SQL:
{previous_sql}

Execution error:
{error}

Return a corrected execution plan. Do not write SQL."""
        return ask(prompt, system=system)

    def _generate_sql(self, question: str, plan: str, ask, error: str = "", previous_sql: str = "", note: str = "") -> str:
        system = "You generate SQLite SQL. Respond with only one SELECT statement and no explanation."
        prompt = f"""Database schema:
{self.schema}

Question:
{question}

Query plan:
{plan}
"""
        if error:
            prompt += f"""
Previous SQL:
{previous_sql}

Execution error:
{error}

Write a corrected SQL query. Only SQL."""
        else:
            if note:
                prompt += f"\n{note}\n"
            prompt += "\nWrite a correct SQL query. Only SQL."

        return ask(prompt, system=system)