"""Generate two independent SQL formulations, execute both, and return the SQL whose result is non-empty, preferring the first when both are non-empty."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )

        join_system = (
            "You are a precise SQL engine. Write one valid SQL query for the question. "
            "Prefer an explicit JOIN-based formulation. Return only SQL."
        )
        subquery_system = (
            "You are a precise SQL engine. Write one valid SQL query for the question. "
            "Prefer a subquery-based formulation using IN, EXISTS, derived tables, or CTEs. "
            "Avoid direct joins when possible. Return only SQL."
        )

        join_sql = self._generate_sql(prompt, join_system)
        subquery_sql = self._generate_sql(prompt, subquery_system)

        join_result = self._execute_sql(join_sql)
        subquery_result = self._execute_sql(subquery_sql)

        if self._has_nonempty_rows(join_result):
            return join_sql

        if self._has_nonempty_rows(subquery_result):
            return subquery_sql

        if join_result.get("ok"):
            return join_sql

        if subquery_result.get("ok"):
            return subquery_sql

        return join_sql or subquery_sql

    def _generate_sql(self, prompt: str, system: str) -> str:
        raw = self._llm_text(prompt, system=system)
        return self._extract_sql(raw)

    def _llm_text(self, prompt: str, system: str) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        if isinstance(response, list):
            return str(response[0]) if response else ""

        if isinstance(response, dict):
            for key in ("text", "content", "output", "completion"):
                if key in response:
                    return str(response[key])

        return str(response or "")

    def _extract_sql(self, text: str) -> str:
        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = None

        extracted = (extracted or "").strip()
        if extracted:
            return extracted

        return (text or "").strip()

    def _execute_sql(self, sql: str) -> dict:
        sql = (sql or "").strip()
        while sql.endswith(";"):
            sql = sql[:-1].strip()

        if not sql:
            return {"ok": False, "rows": [], "error": "empty SQL"}

        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return result

        return {
            "ok": True,
            "rows": result if isinstance(result, list) else [],
            "error": "",
        }

    def _has_nonempty_rows(self, result: dict) -> bool:
        if not isinstance(result, dict):
            return False

        if not result.get("ok"):
            return False

        try:
            return bool(result.get("rows"))
        except Exception:
            return False