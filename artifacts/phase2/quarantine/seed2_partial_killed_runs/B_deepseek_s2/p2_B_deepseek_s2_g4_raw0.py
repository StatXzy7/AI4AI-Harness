"""Generate a SQL query and repair it using execution errors."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS2G4(SQLHarness):
    def solve(self, question: str) -> str:
        system = "You are an expert SQL writer for SQLite. Return only the SQL query, no markdown or explanation."
        prompt = self._build_prompt(question)
        sql = self._extract_sql(self.llm(prompt, system=system, temperature=0.0, n=1))
        if not sql:
            return ""

        max_attempts = 3
        for _ in range(max_attempts):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error") or "Unknown execution error"
            repair_prompt = (
                f"Schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                f"Previous SQL:\n{sql}\n\n"
                f"Execution error: {error}\n\n"
                "Write a corrected SQLite SQL query that answers the question. Return only SQL."
            )
            new_sql = self._extract_sql(
                self.llm(repair_prompt, system=system, temperature=0.0, n=1)
            )
            if not new_sql or new_sql == sql:
                break
            sql = new_sql

        return sql

    def _build_prompt(self, question: str) -> str:
        return (
            f"Given the following SQLite schema:\n{self.schema}\n\n"
            f"Write a SQL query that answers this question: {question}\n"
            "Return only the SQL query, no explanation."
        )

    def _extract_sql(self, raw) -> str:
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        if not isinstance(raw, str):
            raw = str(raw) if raw else ""
        return bridge.extract_sql(raw)