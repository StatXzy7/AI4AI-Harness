"""Two-stage harness that first produces a schema-linking/query plan and then generates the final SQL conditioned on that plan."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS1G5(SQLHarness):
    PLAN_LIMIT = 2000

    def _normalize_llm_response(self, response) -> str:
        if response is None:
            return ""

        if isinstance(response, (list, tuple)):
            return self._normalize_llm_response(response[0]) if response else ""

        if isinstance(response, dict):
            for key in ("text", "completion", "content", "output", "message"):
                if key in response:
                    return self._normalize_llm_response(response[key])
            return str(response)

        if hasattr(response, "choices"):
            choices = getattr(response, "choices", [])
            return self._normalize_llm_response(choices[0]) if choices else ""

        if hasattr(response, "text"):
            return str(getattr(response, "text"))

        return str(response)

    def _llm_text(self, prompt: str, system: str) -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        return self._normalize_llm_response(response)

    def _extract_sql(self, text: str) -> str:
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        sql = (sql or "").strip()
        if sql:
            return sql

        text = (text or "").strip()
        for line in text.splitlines():
            candidate = line.strip().strip("`").strip()
            lowered = candidate.lower()
            if lowered.startswith(("select", "with", "insert", "update", "delete")):
                return candidate

        return text

    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""

        plan_system = (
            "You are a database analyst. Produce only a concise SQL query plan. "
            "Do not write the final SQL."
        )
        plan_prompt = f"""Analyze the schema and question to plan the SQL query.

Schema:
{schema}

Question:
{question}

Return a compact plan containing likely tables, columns, join paths, filters,
aggregations, sorting, and limits. Do not return SQL. Keep it under 200 words.
"""

        plan = self._llm_text(plan_prompt, plan_system).strip()
        if len(plan) > self.PLAN_LIMIT:
            plan = plan[: self.PLAN_LIMIT] + "\n[plan truncated]"
        if not plan:
            plan = "No plan available."

        sql_system = (
            "You are an expert Text-to-SQL system. Output only one executable SQL query."
        )
        sql_prompt = f"""Write the final SQL query for the question.

Use the analysis plan as guidance, but correct it if it appears wrong.

Schema:
{schema}

Question:
{question}

Analysis plan:
{plan}

Return only the SQL query.
"""

        final_text = self._llm_text(sql_prompt, sql_system)
        return self._extract_sql(final_text).strip()