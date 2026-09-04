"""Generates join-based and subquery-based SQL candidates, executes both, and returns the first non-empty result's SQL, otherwise the first candidate."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS0TwoView(SQLHarness):
    def solve(self, question: str) -> str:
        candidates = []
        styles = [
            ("join-based", "Use JOIN clauses (e.g., INNER JOIN ... ON ...) to combine tables."),
            ("subquery-based", "Use subqueries (e.g., IN, EXISTS, scalar subqueries) instead of JOINs where possible."),
        ]

        for style_name, instruction in styles:
            sql = self._generate_sql(question, instruction)
            if sql:
                candidates.append(sql)

        if not candidates:
            return ""

        for sql in candidates:
            try:
                result = self.execute(sql)
            except Exception:
                continue

            if isinstance(result, dict) and result.get("ok") and result.get("rows"):
                return sql

        return candidates[0]

    def _generate_sql(self, question: str, instruction: str) -> str:
        system = "You are an expert SQL engineer. Write only a SQL query, without explanation or markdown fences."
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Style requirement: {instruction}\n"
            "Return only the SQL query."
        )

        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        if isinstance(response, list):
            text = response[0] if response else ""
        else:
            text = response

        try:
            return bridge.extract_sql(text)
        except Exception:
            return ""