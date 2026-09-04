"""Repair-based Text-to-SQL harness that regenerates SQL from execution errors until a query succeeds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS1G2(SQLHarness):
    MAX_ATTEMPTS = 3

    def solve(self, question: str) -> str:
        schema = self.schema
        initial_prompt = self._build_initial_prompt(question, schema)
        sql = self._generate_sql(initial_prompt)

        for attempt in range(self.MAX_ATTEMPTS):
            error = None
            if sql:
                try:
                    result = self.execute(sql)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}

                if result and result.get("ok"):
                    return sql

                error = (result or {}).get("error") or "Unknown execution error."
            else:
                error = "The model produced no SQL."

            if attempt == self.MAX_ATTEMPTS - 1:
                break

            repair_prompt = self._build_repair_prompt(question, schema, sql, error)
            sql = self._generate_sql(repair_prompt)

        return sql or ""

    def _generate_sql(self, prompt: str) -> str:
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        text = self._response_to_text(response)
        return bridge.extract_sql(text)

    @staticmethod
    def _response_to_text(response):
        if isinstance(response, str):
            return response

        if isinstance(response, dict):
            text = response.get("text") or response.get("content") or ""
            choices = response.get("choices") or []
            if not text and choices:
                first = choices[0]
                if isinstance(first, dict):
                    message = first.get("message") or {}
                    text = message.get("content") or first.get("text") or ""
            return text or ""

        if hasattr(response, "choices") and response.choices:
            first = response.choices[0]
            if hasattr(first, "message") and hasattr(first.message, "content"):
                return first.message.content or ""
            if hasattr(first, "text"):
                return first.text or ""

        return str(response or "")

    def _build_initial_prompt(self, question: str, schema: str) -> str:
        return (
            "You are a SQL expert. Given the following database schema, write a single SQL query "
            "that answers the user's question correctly.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Return only SQL."
        )

    def _build_repair_prompt(self, question: str, schema: str, previous_sql: str, error: str) -> str:
        return (
            "You are a SQL expert. A previous SQL query failed against the database.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            f"Previous SQL:\n{previous_sql or '<none>'}\n\n"
            f"Execution error:\n{error}\n\n"
            "Fix the SQL query. Return only SQL."
        )