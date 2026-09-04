"""Executes a generated SQL query and repairs it by feeding execution errors back to the LLM."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G6(SQLHarness):
    _SYSTEM_PROMPT = (
        "You are a highly capable SQL engineer. "
        "Given a database schema and a question, produce a single SQL query that answers the question. "
        "Output only SQL."
    )

    @staticmethod
    def _response_text(response) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, list):
            if not response:
                return ""
            first = response[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    return str(message.get("content") or message.get("text") or first)
                return str(first.get("text") or first.get("content") or first)
            return str(first)
        if isinstance(response, dict):
            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    message = first_choice.get("message")
                    if isinstance(message, dict):
                        return str(message.get("content") or message.get("text") or first_choice)
                    return str(first_choice.get("text") or first_choice.get("content") or first_choice)
                return str(first_choice)
            return str(response.get("text") or response.get("content") or response)
        return str(getattr(response, "text", response))

    def _generate_sql(self, prompt: str) -> str:
        raw_response = self.llm(prompt, system=self._SYSTEM_PROMPT, temperature=0.0, n=1)
        text = self._response_text(raw_response)
        sql = bridge.extract_sql(text)
        return sql if sql else text.strip()

    def solve(self, question: str) -> str:
        schema = self.schema

        initial_prompt = (
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query that answers the question. Output only SQL."
        )

        last_sql = ""
        last_error = "Unknown error"

        for attempt in range(3):
            if attempt == 0:
                prompt = initial_prompt
            else:
                prompt = (
                    f"Database schema:\n{schema}\n\n"
                    f"Question: {question}\n\n"
                    f"The previous SQL query:\n{last_sql}\n\n"
                    f"failed with the following error:\n{last_error}\n\n"
                    "Write a corrected SQL query. Output only SQL."
                )

            sql = self._generate_sql(prompt)
            if not sql:
                continue

            last_sql = sql

            try:
                result = self.execute(sql)
            except Exception as exc:  # noqa: BLE001 - harness boundary
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                return sql

            last_error = result.get("error") or "Unknown error"

        return last_sql if last_sql else "SELECT 1"