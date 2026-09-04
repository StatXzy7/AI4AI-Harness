"""Generates SQL and then repairs it by executing it and feeding execution errors back to the LLM."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G0(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are an expert SQL writer."

        initial_prompt = (
            "You are given a database schema and a question. "
            "Write a valid SQL query that answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only SQL."
        )

        raw = self.llm(initial_prompt, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(self._as_str(raw)) or ""

        max_attempts = 4
        for _ in range(max_attempts):
            if not sql:
                sql = self._repair_no_sql(question, system)
                if not sql:
                    break

            result = self.execute(sql)
            if result.get("ok"):
                return sql.strip()

            error = result.get("error") or "Unknown execution error"
            repair_prompt = (
                "A SQL query was generated but it failed to execute.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Execution error:\n{error}\n\n"
                "Fix the SQL so that it executes successfully while still answering the question. "
                "Return only SQL."
            )

            raw = self.llm(repair_prompt, system=system, temperature=0.0, n=1)
            repaired = bridge.extract_sql(self._as_str(raw))

            if repaired:
                sql = repaired
            else:
                sql = self._fallback_repair(question, sql, error, system)
                if not sql:
                    break

        return sql.strip() if sql else ""

    def _as_str(self, response):
        if isinstance(response, str):
            return response

        if isinstance(response, list):
            for item in response:
                text = self._as_str(item)
                if text:
                    return text
            return ""

        if isinstance(response, dict):
            # Handle common OpenAI-like response shapes.
            for key in ("text", "content", "message", "choices"):
                if key == "choices":
                    choices = response.get(key)
                    if isinstance(choices, list) and choices:
                        return self._as_str(choices[0])
                else:
                    value = response.get(key)
                    if isinstance(value, str):
                        return value
                    if isinstance(value, (dict, list)):
                        text = self._as_str(value)
                        if text:
                            return text
            return str(response.get("text") or response.get("content") or "")

        # Handle objects with text or message attributes.
        if hasattr(response, "text"):
            return str(getattr(response, "text"))
        if hasattr(response, "message"):
            msg = getattr(response, "message")
            if isinstance(msg, str):
                return msg
            if isinstance(msg, dict):
                return self._as_str(msg)
            if hasattr(msg, "content"):
                return str(getattr(msg, "content"))

        return str(response or "")

    def _repair_no_sql(self, question: str, system: str) -> str:
        prompt = (
            "You previously returned an answer that did not contain a SQL query. "
            "Now return only a SQL query for the following question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only SQL."
        )
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(self._as_str(raw))

    def _fallback_repair(self, question: str, previous_sql: str, error: str, system: str) -> str:
        prompt = (
            "The SQL below is wrong. Write one corrected SQL query.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Wrong SQL:\n{previous_sql}\n\n"
            f"Error:\n{error}\n\n"
            "Return only SQL."
        )
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        return bridge.extract_sql(self._as_str(raw))