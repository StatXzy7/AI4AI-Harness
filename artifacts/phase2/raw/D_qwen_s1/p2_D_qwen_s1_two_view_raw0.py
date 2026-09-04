"""Generate two independent SQL formulations, execute both, and prefer the first non-empty result."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS1TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        system = (
            "You are a precise Text-to-SQL engine. "
            "Return only one executable SELECT statement, without explanation."
        )

        join_prompt = (
            "Use the schema below to answer the question with a JOIN-based formulation.\n"
            "Prefer explicit table joins in the FROM clause.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "SQL (JOIN-based):"
        )

        subquery_prompt = (
            "Use the schema below to answer the same question with an independent subquery-based formulation.\n"
            "Prefer subqueries in FROM, WHERE, or SELECT instead of the main join structure.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            "SQL (subquery-based):"
        )

        join_sql = self._make_sql(join_prompt, system)
        subquery_sql = self._make_sql(subquery_prompt, system)

        join_result = self._safe_execute(join_sql)
        subquery_result = self._safe_execute(subquery_sql)

        return self._choose_sql(
            join_sql,
            join_result,
            subquery_sql,
            subquery_result,
        )

    def _make_sql(self, prompt: str, system: str) -> str:
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)

        if isinstance(raw, list):
            raw = "\n".join(str(item) for item in raw)
        else:
            raw = str(raw)

        sql = bridge.extract_sql(raw)
        if not sql:
            sql = raw.strip()

        return sql.strip()

    def _safe_execute(self, sql: str) -> dict:
        if not sql:
            return {"ok": False, "rows": [], "error": "No SQL generated."}

        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if not isinstance(result, dict):
            return {
                "ok": False,
                "rows": [],
                "error": "Executor returned an invalid result.",
            }

        return {
            "ok": bool(result.get("ok", False)),
            "rows": result.get("rows", []),
            "error": result.get("error", ""),
        }

    def _choose_sql(
        self,
        first_sql: str,
        first_result: dict,
        second_sql: str,
        second_result: dict,
    ) -> str:
        candidates = (
            (first_sql, first_result),
            (second_sql, second_result),
        )

        # Prefer the first candidate that executed successfully and returned rows.
        for sql, result in candidates:
            if sql and result.get("ok") and result.get("rows"):
                return sql

        # If neither returned rows, prefer the first candidate that executed successfully.
        for sql, result in candidates:
            if sql and result.get("ok"):
                return sql

        # If neither executed successfully, return the first non-empty SQL text.
        for sql, _ in candidates:
            if sql:
                return sql

        # Last-resort executable SQL.
        return "SELECT 1"