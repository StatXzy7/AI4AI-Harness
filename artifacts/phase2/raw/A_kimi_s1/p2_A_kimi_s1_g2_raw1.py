"""Iteratively repair a greedily generated SQL query by executing it and feeding database errors back to the LLM."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS1G2(SQLHarness):
    """Execution-guided repair harness for Text-to-SQL.

    Control flow:
      1. Generate an initial SQL query greedily (temperature 0).
      2. Execute it against the database.
      3. If execution succeeds, return the query immediately.
      4. Otherwise, build a repair prompt containing the failing SQL and
         the exact database error message, and ask the LLM for a fix.
      5. Repeat for a bounded number of attempts, returning the first
         query that executes successfully; if none does, return the last
         candidate.
    """

    MAX_ATTEMPTS = 4

    SYSTEM_PROMPT = (
        "You are an expert SQLite text-to-SQL engine. Given a database "
        "schema and a natural-language question, you write exactly one "
        "correct SQLite query. You output only SQL: no explanations, no "
        "markdown fences."
    )

    def solve(self, question: str) -> str:
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite query that answers the question. "
            "Return only the SQL query."
        )

        sql = self._generate(base_prompt, temperature=0.0)

        for attempt in range(self.MAX_ATTEMPTS):
            ok, error = self._run(sql)
            if ok:
                return sql

            repair_prompt = (
                "Database schema:\n"
                f"{self.schema}\n\n"
                f"Question: {question}\n\n"
                "A previously written query failed to run on this database.\n\n"
                f"Failing SQL:\n{sql}\n\n"
                f"Database error message:\n{error}\n\n"
                "Diagnose the cause (wrong table or column names, invalid "
                "syntax, bad joins, wrong aggregation, etc.) and write a "
                "corrected SQLite query that answers the question. "
                "Return only the corrected SQL query."
            )
            # The first repair call stays deterministic; later retries get
            # a small temperature bump so a repeated identical failure can
            # escape the deterministic attractor.
            temperature = 0.0 if attempt == 0 else 0.4
            new_sql = self._generate(repair_prompt, temperature=temperature)
            if new_sql:
                sql = new_sql

        return sql

    def _generate(self, prompt: str, temperature: float) -> str:
        response = self.llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=temperature,
            n=1,
        )
        sql = bridge.extract_sql(response)
        if not sql:
            sql = (response or "").strip()
        return sql

    def _run(self, sql: str):
        """Execute SQL defensively; return (ok, error_message)."""
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: treat harness exceptions as DB errors
            return False, str(exc)
        if result.get("ok"):
            return True, ""
        return False, result.get("error") or "unknown execution error"