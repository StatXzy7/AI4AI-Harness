"""Generate two independent SQL formulations, execute both, and return the first formulation that produces non-empty rows."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS2TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "")
        system = (
            "You are an expert Text-to-SQL assistant. "
            "Return only one executable SQL statement, without explanation."
        )

        join_prompt = (
            "Write a SQL query to answer the question using the schema below.\n"
            "Use an explicit JOIN-based formulation.\n"
            "Avoid subqueries, derived tables, and CTEs unless absolutely necessary.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )

        subquery_prompt = (
            "Write a SQL query to answer the same question using the schema below.\n"
            "Use a structurally independent subquery-based formulation, such as subqueries, "
            "derived tables, EXISTS, or CTEs.\n"
            "Avoid explicit JOINs when possible.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )

        candidates = []
        for prompt in (join_prompt, subquery_prompt):
            try:
                response = self.llm(prompt, system=system, temperature=0.0, n=1)
            except Exception:
                response = ""

            if isinstance(response, (list, tuple)):
                response = response[0] if response else ""
            if not isinstance(response, str):
                response = str(response)

            try:
                sql = bridge.extract_sql(response)
            except Exception:
                sql = ""

            if not sql:
                sql = response.strip()

            candidates.append(sql.strip())

        results = []
        for sql in candidates:
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if not isinstance(result, dict):
                result = {"ok": False, "rows": [], "error": "invalid execution result"}

            results.append(result)

        non_empty_indices = [
            i
            for i, result in enumerate(results)
            if result.get("ok") and bool(result.get("rows"))
        ]
        if non_empty_indices:
            return candidates[non_empty_indices[0]]

        executable_indices = [
            i for i, result in enumerate(results) if result.get("ok")
        ]
        if executable_indices:
            return candidates[executable_indices[0]]

        for sql in candidates:
            if sql:
                return sql

        return ""