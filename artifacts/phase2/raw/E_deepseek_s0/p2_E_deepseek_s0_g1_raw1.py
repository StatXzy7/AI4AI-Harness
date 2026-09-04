"""Two-phase plan-then-SQL generation with execution-guided repair for text-to-SQL."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        def ask(prompt: str, system: str = "", temperature: float = 0.0, n: int = 1) -> str:
            response = self.llm(prompt, system=system, temperature=temperature, n=n)
            if isinstance(response, list):
                return response[0] if response else ""
            return response

        # Phase 1: produce a short execution plan before writing SQL.
        plan_prompt = f"""You are an expert SQL planner.

Database schema:
{schema}

Question: {question}

Write a concise step-by-step plan for the SQL query that answers the question.
Do not write SQL yet."""
        plan = ask(
            plan_prompt,
            system="You are a helpful assistant that plans SQL queries.",
            temperature=0.0,
        )

        # Phase 2: generate SQL conditioned on the plan.
        sql_prompt = f"""You are an expert SQL developer.

Database schema:
{schema}

Question: {question}

Step-by-step plan:
{plan}

Write a single SQLite SQL query that answers the question.
Return only the SQL query."""
        sql_response = ask(
            sql_prompt,
            system="You are a helpful assistant that writes SQL queries.",
            temperature=0.0,
        )

        sql = bridge.extract_sql(sql_response)
        if not sql:
            # Last-resort fallback if the SQL extractor cannot find a query.
            sql = sql_response.strip()

        # Execution-guided repair loop.
        max_repairs = 2
        for attempt in range(max_repairs + 1):
            try:
                result = self.execute(sql)
            except Exception as exc:  # pragma: no cover - defensive
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                return sql

            if attempt == max_repairs:
                break

            error = result.get("error", "unknown execution error")
            repair_prompt = f"""You are an expert SQL developer. Fix the SQLite query.

Database schema:
{schema}

Question: {question}

Current SQL:
{sql}

Execution error:
{error}

Return only the corrected SQL query."""
            repair_response = ask(
                repair_prompt,
                system="You are a helpful assistant that fixes SQL queries.",
                temperature=0.0,
            )

            repaired_sql = bridge.extract_sql(repair_response)
            if repaired_sql:
                sql = repaired_sql
            else:
                # If no SQL can be extracted from the repair response, stop early.
                break

        return sql