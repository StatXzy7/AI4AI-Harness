"""A SQL generation harness that repairs invalid SQL by feeding execution errors back to the LLM."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are an expert SQL engineer. Return only the SQL query and no explanation."

        prompt = self._make_initial_prompt(question)
        sql = self._generate_and_extract(prompt, system)

        if sql:
            result = self._execute_safely(sql)
            if result.get("ok"):
                return sql
            last_error = result.get("error") or "Execution failed for unknown reason"
        else:
            last_error = "The model did not produce a SQL query."

        # Repair loop: use the execution error as feedback and ask for corrected SQL.
        for _ in range(2):
            prompt = self._make_repair_prompt(question, sql, last_error)
            new_sql = self._generate_and_extract(prompt, system)

            if not new_sql:
                last_error = "The model did not produce a SQL query in the repair attempt."
                continue

            sql = new_sql
            result = self._execute_safely(sql)

            if result.get("ok"):
                return sql

            last_error = result.get("error") or "Execution failed for unknown reason"

        return sql or ""

    def _make_initial_prompt(self, question: str) -> str:
        return (
            "Write a SQL query that answers the following question.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only the SQL query."
        )

    def _make_repair_prompt(self, question: str, sql, error: str) -> str:
        previous = sql if sql else "(no SQL was generated)"
        return (
            "The SQL query you generated did not execute successfully.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Previous SQL:\n{previous}\n\n"
            f"Execution error:\n{error}\n\n"
            "Write a corrected SQL query that answers the question. Return only the SQL query."
        )

    def _generate_and_extract(self, prompt: str, system: str) -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, str):
            return bridge.extract_sql(response)
        if isinstance(response, dict):
            text = response.get("text") or response.get("completion") or ""
            return bridge.extract_sql(str(text))
        return bridge.extract_sql(str(response))

    def _execute_safely(self, sql: str):
        try:
            return self.execute(sql)
        except Exception as exc:  # noqa: BLE001 - defensive wrapper
            return {"ok": False, "error": str(exc)}