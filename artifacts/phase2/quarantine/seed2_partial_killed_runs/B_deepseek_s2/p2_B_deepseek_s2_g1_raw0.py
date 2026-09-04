"""Repairs SQL queries by executing them and feeding execution errors back to the LLM for regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G1(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        def llm(prompt: str, system: str = "") -> str:
            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            if isinstance(raw, list):
                return raw[0] if raw else ""
            if raw is None:
                return ""
            return raw

        initial_prompt = self._build_prompt(question, schema)
        raw = llm(initial_prompt, system="You are an expert SQL writer.")
        sql = self._extract_sql(raw)
        result = self.execute(sql)

        if result.get("ok"):
            return sql

        previous_sql = sql
        previous_error = result.get("error") or "Unknown execution error"

        for _ in range(3):
            repair_prompt = self._build_repair_prompt(question, schema, previous_sql, previous_error)
            raw = llm(repair_prompt, system="You are an expert SQL writer. Fix the query.")
            sql = self._extract_sql(raw)
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            previous_sql = sql
            previous_error = result.get("error") or "Unknown execution error"

        return previous_sql

    def _extract_sql(self, raw: str) -> str:
        extracted = bridge.extract_sql(raw)
        if extracted and extracted.strip():
            return extracted.strip()
        return raw.strip()

    def _build_prompt(self, question: str, schema: str) -> str:
        return (
            "Write a SQL query for the following question.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query."
        )

    def _build_repair_prompt(self, question: str, schema: str, previous_sql: str, error: str) -> str:
        return (
            "The following SQL query was generated for the question but produced an execution error.\n"
            "Please fix the SQL based on the schema and error.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            f"Previous SQL:\n{previous_sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Return only the corrected SQL query."
        )