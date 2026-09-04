"""Generate SQLite for the question, execute it, and on failure regenerate the query up to 2 times with the exact SQLite error fed back into the prompt."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS0Repair"]


class P2P2CGlmS0Repair(SQLHarness):
    """Weak Text-to-SQL solver wrapped in an execution-driven repair loop.

    Control flow implemented in code (not merely in the prompt):

        1. Ask the frozen LLM for one SQLite query given (schema, question).
        2. Execute the extracted query via ``self.execute``.
        3. If execution fails, quote the failed query *and the exact SQLite
           error* in a repair prompt, regenerate, and re-execute.
        4. Repeat step 3 at most ``MAX_REPAIRS`` (2) times.
        5. Return the last generated SQL, whether or not it finally executes.
    """

    MAX_REPAIRS = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. Given a database schema and a "
        "natural-language question, answer with exactly one SQLite query that "
        "answers the question. Output only the SQL query itself: no "
        "explanations, no markdown fences."
    )

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite query that answers the question. "
            "Respond with the SQL query only."
        )

    def _repair_prompt(self, question: str, failed_sql: str, error: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Your previous SQL query was:\n"
            f"{failed_sql}\n\n"
            "Executing that query against the database failed with this exact "
            "SQLite error:\n"
            f"{error}\n\n"
            "Write a corrected SQLite query that avoids this error and still "
            "answers the question. Respond with the SQL query only."
        )

    # ------------------------------------------------------------------ #
    # LLM / execution plumbing
    # ------------------------------------------------------------------ #

    def _generate_sql(self, prompt: str) -> str:
        """One deterministic LLM call, reduced to a bare SQL string."""
        text = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        if isinstance(text, (list, tuple)):
            # Tolerate front-ends that return a list even for n=1.
            text = text[0] if text else ""
        if not text:
            return ""
        sql = bridge.extract_sql(str(text))
        return (sql or "").strip()

    def _run_sql(self, sql: str) -> dict:
        """Execute ``sql`` via ``self.execute``; every failure becomes a dict."""
        if not sql:
            return {"ok": False, "rows": [], "error": "No SQL statement was produced."}
        try:
            result = self.execute(sql)
        except Exception as exc:  # a raising executor still counts as failure
            return {"ok": False, "rows": [], "error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "Executor returned no result."}
        return result

    @staticmethod
    def _error_text(result: dict) -> str:
        """The exact error string reported by the executor (never empty)."""
        error = result.get("error")
        return str(error) if error else "Unknown SQLite execution error."

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        # Round 0: initial generation, then execution.
        sql = self._generate_sql(self._initial_prompt(question))
        result = self._run_sql(sql)
        if result.get("ok"):
            return sql

        # Rounds 1..MAX_REPAIRS: feed the exact SQLite error back,
        # regenerate, and re-execute -- at most 2 times.
        for _ in range(self.MAX_REPAIRS):
            error = self._error_text(result)  # verbatim SQLite error message
            sql = self._generate_sql(self._repair_prompt(question, sql, error))
            result = self._run_sql(sql)
            if result.get("ok"):
                return sql

        # Repair budget exhausted: return the last SQL we produced.
        return sql