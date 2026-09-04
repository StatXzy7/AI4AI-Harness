"""Generates two SQL formulations (join-based and subquery-based), executes both, and returns the first SQL whose result set is non-empty."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        join_sql = self._generate(question, "join-based")
        subquery_sql = self._generate(question, "subquery-based")

        join_result = self._execute(join_sql) if join_sql else None
        subquery_result = self._execute(subquery_sql) if subquery_sql else None

        if self._is_nonempty(join_result):
            return join_sql

        if self._is_nonempty(subquery_result):
            return subquery_sql

        return join_sql or subquery_sql

    def _generate(self, question: str, formulation: str) -> str:
        prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Write a single SQL query ({formulation}) that answers the question. "
            "Output only SQL without markdown."
        )

        response = self.llm(prompt, system="", temperature=0.0, n=1)

        if isinstance(response, list):
            response = response[0] if response else ""

        if not isinstance(response, str):
            response = str(response)

        return bridge.extract_sql(response) or ""

    def _execute(self, sql: str):
        try:
            return self.execute(sql)
        except Exception:
            return {"ok": False, "rows": [], "error": "exception"}

    @staticmethod
    def _is_nonempty(result) -> bool:
        return bool(
            isinstance(result, dict)
            and result.get("ok")
            and result.get("rows")
        )