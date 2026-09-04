"""Generate join-based and subquery-based SQL candidates, execute both, and return the SQL whose result is non-empty (preferring the first if both succeed)."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        join_prompt = self._make_prompt(question, "join-based")
        subquery_prompt = self._make_prompt(question, "subquery-based")

        join_sql = self._llm_sql(join_prompt)
        subquery_sql = self._llm_sql(subquery_prompt)

        join_result = self._execute_sql(join_sql)
        subquery_result = self._execute_sql(subquery_sql)

        join_nonempty = bool(join_result.get("ok") and join_result.get("rows"))
        subquery_nonempty = bool(subquery_result.get("ok") and subquery_result.get("rows"))

        if join_nonempty:
            return join_sql
        if subquery_nonempty:
            return subquery_sql

        # Neither candidate produced a non-empty result; return the first generated SQL as a fallback.
        return join_sql or subquery_sql

    def _make_prompt(self, question: str, style: str) -> str:
        if style == "join-based":
            instruction = (
                "Write a SQL query that answers the question using explicit JOINs. "
                "Avoid subqueries in the FROM or WHERE clauses when possible."
            )
        else:
            instruction = (
                "Write a SQL query that answers the question using subqueries "
                "(or CTEs) as the primary mechanism, even if a JOIN-based alternative exists."
            )

        return (
            f"{instruction}\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL statement, without explanation or markdown fences."
        )

    def _llm_sql(self, prompt: str) -> str:
        raw = self.llm(prompt, system="", temperature=0.0, n=1)
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        return bridge.extract_sql(raw)

    def _execute_sql(self, sql: str) -> dict:
        if not sql:
            return {"ok": False, "rows": [], "error": "empty SQL"}
        return self.execute(sql)