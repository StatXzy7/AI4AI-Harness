"""Generate SQL, execute it, and feed execution errors back for repair."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS1G5(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema or ""
        max_repairs = 3

        sql = self._generate_sql(self._initial_prompt(question, schema))

        for _ in range(max_repairs):
            if not sql:
                sql = self._generate_sql(
                    self._repair_prompt(question, schema, "", "No SQL was produced.")
                )
                continue

            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                return sql

            error = result.get("error") or "Unknown execution error"
            sql = self._generate_sql(
                self._repair_prompt(question, schema, sql, error)
            )

        return sql or ""

    def _initial_prompt(self, question: str, schema: str) -> str:
        return (
            "Convert the natural-language question into a single valid SQL query.\n"
            "Use only the provided schema.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n"
            "Return only the SQL query, without markdown fences."
        )

    def _repair_prompt(self, question: str, schema: str, sql: str, error: str) -> str:
        if not sql:
            return (
                "Convert the natural-language question into a single valid SQL query.\n"
                "Use only the provided schema.\n\n"
                f"Schema:\n{schema}\n\n"
                f"Question: {question}\n"
                "The previous response did not contain a SQL query. "
                "Return only the SQL query, without markdown fences."
            )

        return (
            "The following SQL query was generated for a natural-language question, "
            "but it failed to execute.\n"
            "Fix the SQL query using the error message and schema below.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            f"SQL:\n{sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Return only the corrected SQL query, without markdown fences."
        )

    def _generate_sql(self, prompt: str) -> str:
        raw = self.llm(
            prompt,
            system="You are a helpful text-to-SQL assistant. Output only SQL.",
            temperature=0.0,
            n=1,
        )

        if isinstance(raw, list):
            text = raw[0] if raw else ""
        else:
            text = raw

        return bridge.extract_sql(text)