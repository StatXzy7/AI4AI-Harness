"""Executes generated SQL and uses any execution error as feedback to request a corrected SQL query."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G2(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        sql = self._generate_sql(prompt)

        # Try the initial SQL, then repair based on execution errors.
        for _ in range(2):
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                return sql

            error = result.get("error") or "Unknown execution error"
            repair_prompt = self._build_repair_prompt(question, sql, error)
            sql = self._generate_sql(repair_prompt)

        # After the final repair, run it once more to allow early return if successful.
        try:
            final_result = self.execute(sql)
        except Exception:
            final_result = {"ok": False}

        if final_result.get("ok"):
            return sql

        return sql

    def _build_prompt(self, question: str) -> str:
        return (
            "You are an expert SQL writer. Given the database schema and a natural "
            "language question, produce a single SQL query that answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only the SQL query."
        )

    def _build_repair_prompt(self, question: str, previous_sql: str, error: str) -> str:
        return (
            "You are an expert SQL writer. A previously generated SQL query failed "
            "with an execution error. Please fix the SQL query.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Previous SQL:\n{previous_sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Return only the corrected SQL query."
        )

    def _generate_sql(self, prompt: str) -> str:
        raw = self._llm(prompt)
        return bridge.extract_sql(raw)

    def _llm(self, prompt: str) -> str:
        response = self.llm(prompt, system="", temperature=0.0, n=1)

        if isinstance(response, str):
            return response

        if isinstance(response, list) and response:
            first = response[0]
            if isinstance(first, str):
                return first
            return str(first)

        if isinstance(response, dict):
            # Support common LLM response wrappers.
            for key in ("text", "content", "message"):
                value = response.get(key)
                if isinstance(value, str):
                    return value
                if isinstance(value, dict):
                    inner = value.get("content")
                    if isinstance(inner, str):
                        return inner

            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    for key in ("text", "content", "message"):
                        value = first.get(key)
                        if isinstance(value, str):
                            return value
                        if isinstance(value, dict):
                            inner = value.get("content")
                            if isinstance(inner, str):
                                return inner
                    return str(first)
                return str(first)

        return str(response)