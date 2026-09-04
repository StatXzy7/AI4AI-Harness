"""Executes candidate SQL and uses execution errors to ask the LLM for a corrected query."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2ADeepseekS0G1(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        sql = self._extract_sql(self._call_llm(self._make_prompt(question, schema)))
        if not sql:
            sql = "SELECT 1"

        # Attempt a small number of execution-informed repairs.
        for _ in range(2):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error") or "Unknown execution error"
            previous_sql = sql
            repaired_raw = self._call_llm(
                self._make_repair_prompt(question, schema, previous_sql, error)
            )
            sql = self._extract_sql(repaired_raw)
            if not sql:
                return previous_sql

        return sql

    def _call_llm(self, prompt: str) -> str:
        res = self.llm(prompt, system="", temperature=0.0, n=1)
        if isinstance(res, list):
            return "\n".join(str(x) for x in res)
        return str(res)

    def _extract_sql(self, text: str) -> str:
        sql = bridge.extract_sql(text)
        return sql or text.strip()

    def _make_prompt(self, question: str, schema: str) -> str:
        return (
            "You are an expert SQL generator. Given the following database schema and "
            "question, write a single SQLite query that answers the question.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only the SQL query."
        )

    def _make_repair_prompt(self, question: str, schema: str, sql: str, error: str) -> str:
        return (
            "You are an expert SQL generator. The following SQL query failed to execute.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Previous SQL:\n{sql}\n\n"
            f"Execution error:\n{error}\n\n"
            "Write a corrected SQLite query that answers the question. Return only the SQL query."
        )