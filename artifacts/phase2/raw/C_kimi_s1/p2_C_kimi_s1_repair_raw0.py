"""Harness that generates SQL with the frozen LLM, executes it against SQLite, and on failure feeds the exact SQLite error back for up to two repair regenerations."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS1Repair(SQLHarness):
    """Execute-and-repair Text-to-SQL harness.

    Control flow:
      1. Generate an initial SQL candidate from (schema, question).
      2. Execute it via self.execute().
      3. If SQLite reports an error, show the LLM the failing SQL together
         with the exact error message and regenerate -- at most MAX_REPAIRS
         times.
      4. Return the first candidate that executes successfully; otherwise
         return the last candidate generated (best effort).
    """

    MAX_REPAIRS = 2

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL engine for SQLite. "
        "Given a database schema and a natural-language question, you output "
        "exactly one syntactically valid SQLite query and nothing else."
    )

    def solve(self, question: str) -> str:
        sql = self._generate(self._initial_prompt(question))

        for repair_attempt in range(self.MAX_REPAIRS + 1):
            result = self._run(sql)
            if result.get("ok"):
                return sql
            if repair_attempt >= self.MAX_REPAIRS:
                break
            error_message = result.get("error") or "Unknown SQLite error."
            sql = self._generate(
                self._repair_prompt(question, sql, error_message)
            )

        return sql

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _generate(self, prompt: str) -> str:
        """Call the frozen LLM once and extract a SQL string from its output."""
        response = self.llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=0.0,
            n=1,
        )
        if isinstance(response, (list, tuple)):
            text = response[0] if response else ""
        else:
            text = response or ""
        sql = bridge.extract_sql(text)
        if not sql:
            sql = text.strip()
        return sql

    def _run(self, sql: str) -> dict:
        """Execute SQL defensively; convert any raised exception into an error dict."""
        try:
            return self.execute(sql)
        except Exception as exc:  # treat harness/DB crashes as execution failures
            return {"ok": False, "rows": [], "error": str(exc)}

    def _initial_prompt(self, question: str) -> str:
        return (
            "You are given the following SQLite database schema:\n\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SQL query that correctly answers the "
            "question. Output only the SQL query, with no explanation and no "
            "markdown formatting."
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            "You are given the following SQLite database schema:\n\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "The SQL query you previously produced failed when executed "
            "against the SQLite database.\n\n"
            "Failing SQL query:\n"
            f"{bad_sql}\n\n"
            "Exact SQLite error message:\n"
            f"{error}\n\n"
            "Diagnose the cause of this exact error (e.g., wrong table or "
            "column names, invalid syntax, bad literals) and rewrite the "
            "query so that it executes successfully and answers the "
            "question. Output only the corrected SQL query, with no "
            "explanation and no markdown formatting."
        )