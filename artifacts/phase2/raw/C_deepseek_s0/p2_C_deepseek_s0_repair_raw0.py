"""Generate SQL, execute it, and on error feed the exact SQLite message back for up to two repair attempts."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS0Repair(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        current_sql = ""
        last_error = ""
        max_repairs = 2

        for attempt in range(max_repairs + 1):
            if attempt == 0:
                prompt = self._build_initial_prompt(question, schema)
            else:
                prompt = self._build_repair_prompt(
                    question, schema, current_sql, last_error
                )

            raw_response = self.llm(prompt, system="", temperature=0.0, n=1)
            response_text = self._extract_text(raw_response)
            sql = bridge.extract_sql(response_text)

            if not sql:
                sql = response_text.strip()

            current_sql = sql

            if not sql:
                last_error = "Model returned no SQL."
                continue

            result = self.execute(sql)

            if result.get("ok"):
                return sql

            last_error = result.get("error", "Unknown execution error")

        return current_sql

    def _build_initial_prompt(self, question: str, schema: str) -> str:
        return (
            f"Given the following SQLite schema:\n{schema}\n\n"
            f"Write a SQLite SELECT query to answer the question.\n"
            f"Return only the SQL query, no explanation.\n"
            f"Question: {question}\nSQL:"
        )

    def _build_repair_prompt(
        self, question: str, schema: str, previous_sql: str, error: str
    ) -> str:
        return (
            f"Given the following SQLite schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            f"The previous SQL query was:\n{previous_sql}\n\n"
            f"It failed with this SQLite error:\n{error}\n\n"
            f"Please fix the SQL query. Return only the corrected SQLite query, no explanation.\nSQL:"
        )

    @staticmethod
    def _extract_text(response) -> str:
        if isinstance(response, str):
            return response

        if isinstance(response, list):
            if response and isinstance(response[0], str):
                return response[0]
            return str(response)

        if isinstance(response, dict):
            try:
                return response["choices"][0]["message"]["content"]
            except Exception:
                pass
            try:
                return response["choices"][0]["text"]
            except Exception:
                pass

        return str(response)