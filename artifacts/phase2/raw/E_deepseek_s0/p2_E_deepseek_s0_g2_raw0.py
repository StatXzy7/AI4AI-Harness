"""Harness that drafts SQL, executes it against the database, and repairs errors iteratively for up to three attempts."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2EDeepseekS0G2(SQLHarness):
    MAX_ATTEMPTS = 3

    def solve(self, question: str) -> str:
        prompt = self._build_initial_prompt(question)
        raw = self._call_llm(prompt)
        sql = bridge.extract_sql(raw) or raw.strip()
        last_sql = sql.strip()

        for _ in range(self.MAX_ATTEMPTS):
            if not last_sql:
                prompt = self._build_repair_prompt(
                    question,
                    last_sql or "(empty)",
                    "The previous response did not contain a SQL query.",
                )
                raw = self._call_llm(prompt)
                last_sql = (bridge.extract_sql(raw) or raw).strip()
                continue

            result = self._safe_execute(last_sql)
            if result.get("ok"):
                return last_sql

            error = result.get("error") or "Unknown execution error"
            prompt = self._build_repair_prompt(question, last_sql, error)
            raw = self._call_llm(prompt)
            extracted = (bridge.extract_sql(raw) or raw).strip()
            if extracted:
                last_sql = extracted

        return last_sql

    def _call_llm(self, prompt: str) -> str:
        response = self.llm(
            prompt,
            system="You are a careful SQLite query generator.",
            temperature=0.0,
            n=1,
        )
        if isinstance(response, list):
            return response[0] if response else ""
        return str(response)

    def _safe_execute(self, sql: str):
        try:
            return self.execute(sql)
        except Exception as exc:  # defensive: some harnesses may raise
            return {"ok": False, "rows": [], "error": str(exc)}

    def _build_initial_prompt(self, question: str) -> str:
        return (
            "Write a single SQLite query that answers the question.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only the SQL query and no additional text."
        )

    def _build_repair_prompt(self, question: str, previous_sql: str, error: str) -> str:
        return (
            "The following SQLite query generated for the question is invalid or produced an error.\n\n"
            f"Previous SQL:\n{previous_sql}\n\n"
            f"Error:\n{error}\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Write a corrected SQLite query. Return only the SQL query and no additional text."
        )