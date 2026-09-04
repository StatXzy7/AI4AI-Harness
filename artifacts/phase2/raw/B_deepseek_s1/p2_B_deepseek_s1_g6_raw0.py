"""Repair-based Text-to-SQL harness that regenerates a query using execution feedback after a failed candidate."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS1G6(SQLHarness):
    MAX_REPAIR_ATTEMPTS = 2

    def solve(self, question: str) -> str:
        system_prompt = "You are an expert SQL engineer. Return only SQL."
        prompt = self._build_initial_prompt(question)
        raw = self._call_llm(prompt, system_prompt)
        sql = self._extract_sql(raw) or raw.strip()

        for attempt in range(self.MAX_REPAIR_ATTEMPTS + 1):
            if sql:
                result = self.execute(sql)
            else:
                result = None

            if result and result.get("ok"):
                return sql

            error = "No SQL was produced."
            if result is not None:
                error = result.get("error") or "Unknown execution error"

            if attempt >= self.MAX_REPAIR_ATTEMPTS:
                break

            repair_prompt = self._build_repair_prompt(question, sql, error)
            raw = self._call_llm(repair_prompt, system_prompt)
            new_sql = self._extract_sql(raw) or raw.strip()

            if new_sql.strip() == sql.strip():
                continue

            sql = new_sql.strip()

        return sql or ""

    def _call_llm(self, prompt: str, system: str) -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, list):
            return response[0] if response else ""
        return response or ""

    def _extract_sql(self, text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            return ""
        extracted = bridge.extract_sql(text)
        return extracted.strip() if extracted and extracted.strip() else ""

    def _build_initial_prompt(self, question: str) -> str:
        return (
            "Write a SQL query for the following question using the database schema below.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )

    def _build_repair_prompt(self, question: str, sql: str, error: str) -> str:
        return (
            "The following SQL query for the question failed to execute.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Previous SQL:\n{sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Fix the SQL query and return only the corrected SQL.\n\n"
            "SQL:"
        )