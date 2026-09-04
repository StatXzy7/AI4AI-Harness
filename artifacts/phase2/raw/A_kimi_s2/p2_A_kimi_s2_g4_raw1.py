"""Text-to-SQL harness that executes candidate SQL and repairs failures by feeding execution errors back to the LLM."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G4(SQLHarness):
    """Generate SQL greedily, execute it, and on failure regenerate with
    the execution error message as feedback, up to a bounded number of
    attempts. Returns the first SQL that executes successfully."""

    MAX_ATTEMPTS = 4

    SYSTEM_PROMPT = (
        "You are an expert SQL generator. Given a database schema and a "
        "natural-language question, produce exactly one correct SQL query. "
        "Output only the SQL query itself: no explanation, no comments, "
        "no markdown fences."
    )

    def _generate(self, prompt: str) -> str:
        response = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0)
        sql = bridge.extract_sql(response)
        if not sql:
            sql = (response or "").strip()
        return sql

    def solve(self, question: str) -> str:
        initial_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question."
        )
        sql = self._generate(initial_prompt)

        for attempt in range(self.MAX_ATTEMPTS):
            if not sql:
                sql = self._generate(initial_prompt)
            result = self.execute(sql)
            if result.get("ok"):
                return sql
            if attempt == self.MAX_ATTEMPTS - 1:
                break
            error = result.get("error") or "unknown execution error"
            repair_prompt = (
                f"Database schema:\n{self.schema}\n\n"
                f"Question: {question}\n\n"
                "The following SQL query failed to execute:\n"
                f"{sql}\n\n"
                f"The database returned this error:\n{error}\n\n"
                "Diagnose the cause of the error and output a single "
                "corrected SQL query that answers the question. Output "
                "only the corrected SQL."
            )
            sql = self._generate(repair_prompt)

        # All attempts failed; return the last candidate as a fallback.
        return sql