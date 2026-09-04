"""Generate two independent SQL formulations and return the first executed query that produces non-empty rows."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS1TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        join_system = (
            "You are a SQL expert. Produce only one executable SQL query. "
            "Prefer explicit JOINs and direct table relationships."
        )
        subquery_system = (
            "You are a SQL expert. Produce only one executable SQL query. "
            "Prefer subqueries, CTEs, or derived tables rather than the obvious join formulation."
        )

        join_prompt = (
            "Given the schema below, answer the question with one SELECT statement.\n"
            "Use an explicit join-based formulation.\n"
            "Do not include explanations.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )
        subquery_prompt = (
            "Given the schema below, answer the question with one SELECT statement.\n"
            "Use an independent subquery-based or derived-table formulation, avoiding the same join structure if possible.\n"
            "Do not include explanations.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )

        sqls = [
            self._generate_sql(join_prompt, join_system),
            self._generate_sql(subquery_prompt, subquery_system),
        ]

        results = [self._execute_safe(sql) for sql in sqls]

        first_result, second_result = results

        if first_result.get("ok") and first_result.get("rows"):
            return sqls[0]

        if second_result.get("ok") and second_result.get("rows"):
            return sqls[1]

        return sqls[0]

    def _generate_sql(self, prompt: str, system: str) -> str:
        try:
            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            raw = ""

        text = self._completion_text(raw)

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        if extracted is None:
            extracted = text

        return str(extracted).strip()

    def _completion_text(self, completion) -> str:
        if completion is None:
            return ""

        if isinstance(completion, str):
            return completion

        if isinstance(completion, list):
            return self._completion_text(completion[0]) if completion else ""

        if isinstance(completion, dict):
            for key in ("text", "completion", "content", "output"):
                if key in completion:
                    return self._completion_text(completion[key])

            if "choices" in completion:
                choices = completion.get("choices") or []
                if choices:
                    return self._completion_text(choices[0])

            if "message" in completion:
                return self._completion_text(completion["message"])

        return str(completion)

    def _execute_safe(self, sql: str):
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if not isinstance(result, dict):
            return {
                "ok": True,
                "rows": result if isinstance(result, list) else [],
                "error": "",
            }

        return {
            "ok": bool(result.get("ok", False)),
            "rows": result.get("rows", []),
            "error": result.get("error", ""),
        }