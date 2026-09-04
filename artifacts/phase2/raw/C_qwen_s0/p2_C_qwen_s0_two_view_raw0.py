"""Generate join-based and subquery-based SQL candidates, execute both, and return the first successful non-empty result."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS0TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL system. "
            "Return only one complete SQL statement, with no explanation."
        )

        join_prompt = (
            "Write a SQL query that answers the question using an explicit join-based formulation.\n"
            "Prefer JOIN ... ON clauses where possible.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )

        subquery_prompt = (
            "Write a SQL query that answers the same question using an independent subquery-based formulation.\n"
            "Prefer subqueries, CTEs, EXISTS, or IN where possible instead of the main join pattern.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )

        join_text = self.llm(join_prompt, system=system, temperature=0.0, n=1)
        subquery_text = self.llm(subquery_prompt, system=system, temperature=0.0, n=1)

        join_sql = self._extract_sql(join_text)
        subquery_sql = self._extract_sql(subquery_text)

        join_result = self._execute(join_sql)
        subquery_result = self._execute(subquery_sql)

        join_has_rows = bool(join_result.get("ok") and join_result.get("rows"))
        subquery_has_rows = bool(subquery_result.get("ok") and subquery_result.get("rows"))

        if join_sql and join_has_rows:
            return join_sql

        if subquery_sql and subquery_has_rows:
            return subquery_sql

        if join_sql and join_result.get("ok"):
            return join_sql

        if subquery_sql and subquery_result.get("ok"):
            return subquery_sql

        return join_sql or subquery_sql

    def _extract_sql(self, text) -> str:
        raw = "" if text is None else str(text)
        try:
            extracted = bridge.extract_sql(raw)
        except Exception:
            extracted = raw

        extracted = "" if extracted is None else str(extracted)
        extracted = extracted.strip()

        if extracted:
            return extracted

        return raw.strip()

    def _execute(self, sql: str):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "invalid execution result"}

        return result