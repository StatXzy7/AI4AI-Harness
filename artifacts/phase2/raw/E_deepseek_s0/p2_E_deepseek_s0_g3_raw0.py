"""Two-phase plan-to-prompt SQL generation with execution-guided repair for the Deepseek target."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G3(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        # 1) Schema-linking / planning pass.
        plan_prompt = f"""You are given a SQLite database schema and a natural-language question.
Produce a concise analysis to guide correct SQL generation.
Identify relevant tables/columns, join conditions, filter values, aggregations, and any ambiguity.
Do not write SQL.

Schema:
{schema}

Question:
{question}

Analysis:
"""
        plan_raw = self._llm_text(plan_prompt, "You are a meticulous SQL planning assistant.")
        plan = plan_raw.strip()

        # 2) Generate an initial SQL query conditioned on the plan.
        sql = self._generate_from_plan(question, schema, plan)

        # 3) Execution-guided repair loop.
        for _ in range(3):
            result = self._execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "Unknown execution error")
            repaired = self._repair(question, schema, sql, error)
            if not repaired or repaired.lower() == sql.lower():
                break
            sql = repaired

        # 4) Final independent generation attempt as a fallback.
        final_sql = self._generate_direct(question, schema)
        if final_sql:
            final_result = self._execute(final_sql)
            if final_result.get("ok"):
                return final_sql

        return sql or "SELECT 1"

    def _llm_text(self, prompt: str, system: str) -> str:
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        return raw if isinstance(raw, str) else str(raw)

    def _extract_sql(self, text: str) -> str:
        text = text or ""
        sql = bridge.extract_sql(text)
        if sql:
            return sql
        return text.strip().rstrip(";").strip()

    def _execute(self, sql: str):
        if not sql:
            return {"ok": False, "error": "No SQL query generated"}
        return self.execute(sql)

    def _generate_from_plan(self, question: str, schema: str, plan: str) -> str:
        prompt = f"""Using the analysis below, write one SQLite SELECT query that answers the question.
Return only the SQL query, with no explanation.

Schema:
{schema}

Question:
{question}

Analysis:
{plan}

SQL:
"""
        raw = self._llm_text(prompt, "You are a SQLite SQL generation assistant.")
        return self._extract_sql(raw)

    def _repair(self, question: str, schema: str, sql: str, error: str) -> str:
        prompt = f"""A previous SQLite query failed with an execution error.
Write a corrected SQLite SELECT query.
Return only the SQL query, with no explanation.

Schema:
{schema}

Question:
{question}

Previous SQL:
{sql}

Error:
{error}

Corrected SQL:
"""
        raw = self._llm_text(prompt, "You are a SQLite SQL debugging assistant.")
        return self._extract_sql(raw)

    def _generate_direct(self, question: str, schema: str) -> str:
        prompt = f"""Write one SQLite SELECT query that answers the question.
Return only the SQL query, with no explanation.

Schema:
{schema}

Question:
{question}

SQL:
"""
        raw = self._llm_text(prompt, "You are a SQLite SQL generation assistant.")
        return self._extract_sql(raw)