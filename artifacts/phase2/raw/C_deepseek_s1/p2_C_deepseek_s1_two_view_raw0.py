"""Generate two SQL formulations (join-based and subquery-based) and return the first whose execution yields non-empty rows."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS1TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        join_sql = self._generate_sql(question, "join-based")
        subquery_sql = self._generate_sql(question, "subquery-based")

        join_result = self.execute(join_sql)
        subquery_result = self.execute(subquery_sql)

        if self._non_empty(join_result):
            return join_sql
        if self._non_empty(subquery_result):
            return subquery_sql

        # If both are empty, return the first formulation as a fallback.
        return join_sql

    def _generate_sql(self, question: str, formulation: str) -> str:
        system = "You are a precise text-to-SQL assistant. Return only SQL."
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a {formulation} SQL query. Use {formulation} structure. Return only the SQL."
        )

        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(raw, list):
            raw = raw[0] if raw else ""

        sql = bridge.extract_sql(raw)
        return sql or raw.strip()

    @staticmethod
    def _non_empty(result: dict) -> bool:
        return bool(result and result.get("ok") and result.get("rows"))