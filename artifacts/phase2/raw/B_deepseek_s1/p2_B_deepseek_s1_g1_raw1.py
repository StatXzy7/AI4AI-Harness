"""Repair-based SQL generation that uses execution errors to retry and fix candidate queries."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge

class P2P2BDeepseekS1G1(SQLHarness):
    def solve(self, question: str) -> str:
        system_prompt = "You are an expert SQL query generator. Always return only the SQL query."
        sql = self._generate_initial_sql(question, system_prompt)
        best_sql = sql

        max_repairs = 2
        for _ in range(max_repairs):
            if not sql:
                error = "The model did not return a SQL query."
            else:
                result = self._safe_execute(sql)
                if result.get("ok"):
                    return sql
                error = result.get("error", "Unknown execution error")
                best_sql = sql

            sql = self._repair_sql(question, sql, error, system_prompt)

        if sql:
            result = self._safe_execute(sql)
            if result.get("ok"):
                return sql
            best_sql = sql

        return best_sql or sql or ""

    def _generate_initial_sql(self, question: str, system_prompt: str) -> str:
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write the SQL query that answers the question. Return only SQL."
        )
        response = self.llm(prompt, system=system_prompt, temperature=0.0, n=1)
        text = self._response_to_text(response)
        sql = bridge.extract_sql(text)
        return sql or text.strip()

    def _repair_sql(self, question: str, previous_sql: str, error: str, system_prompt: str) -> str:
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Your previous SQL query:\n{previous_sql}\n\n"
            f"Execution error:\n{error}\n\n"
            f"Write a corrected SQL query. Return only SQL."
        )
        response = self.llm(prompt, system=system_prompt, temperature=0.0, n=1)
        text = self._response_to_text(response)
        sql = bridge.extract_sql(text)
        return sql or text.strip()

    def _safe_execute(self, sql: str):
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    def _response_to_text(self, response) -> str:
        if response is None:
            return ""
        if isinstance(response, list):
            return "\n".join(str(item) for item in response)
        return str(response)