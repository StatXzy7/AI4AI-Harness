"""Generate a candidate SQL query, execute it, and use execution errors to iteratively repair the SQL with the LLM."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS2G2(SQLHarness):
    MAX_REPAIR_ATTEMPTS = 3

    def solve(self, question: str) -> str:
        prompt = self._build_initial_prompt(question)
        response = self._llm_text(prompt)
        sql = bridge.extract_sql(response)

        if not sql:
            error = "No SQL found in the model response."
        else:
            ok, error = self._execute_sql(sql)
            if ok:
                return sql

        current_sql = sql

        for _ in range(self.MAX_REPAIR_ATTEMPTS):
            prompt = self._build_repair_prompt(question, current_sql, error)
            response = self._llm_text(prompt)
            repaired_sql = bridge.extract_sql(response)

            if not repaired_sql:
                error = "No SQL found in the model response."
                continue

            current_sql = repaired_sql
            ok, error = self._execute_sql(current_sql)
            if ok:
                return current_sql

        return current_sql or ""

    def _build_initial_prompt(self, question: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query that answers the question. Return only SQL."
        )

    def _build_repair_prompt(self, question: str, sql: str, error: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"The following SQL query was generated but failed to execute:\n"
            f"SQL:\n{sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Please fix the SQL query. Return only SQL."
        )

    def _llm_text(self, prompt: str) -> str:
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        if isinstance(response, list):
            return str(response[0]) if response else ""
        return str(response)

    def _execute_sql(self, sql: str):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

        if result.get("ok"):
            return True, ""
        return False, result.get("error") or "Unknown execution error"