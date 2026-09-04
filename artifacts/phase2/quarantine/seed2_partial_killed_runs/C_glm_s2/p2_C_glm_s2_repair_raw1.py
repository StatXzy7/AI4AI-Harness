"""Repair harness: generate SQL with a frozen weak solver, execute it, and if execution fails, feed the exact SQLite error back to the generator to regenerate the SQL, up to 2 times."""

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS2Repair"]


class P2P2CGlmS2Repair(SQLHarness):
    """Generate -> execute -> (on error) repair using the exact error message.

    Control flow:
      1. Ask the weak solver for one SQLite SELECT statement.
      2. Execute it via self.execute().
      3. If execution fails, show the solver its failed SQL plus the exact
         SQLite error string and ask for a corrected statement.
      4. Re-execute; repeat the repair at most MAX_REPAIR_ROUNDS (2) times.
      5. Return the last SQL produced (whether or not it finally executes).
    """

    MAX_REPAIR_ROUNDS = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite assistant. Given a database schema and a "
        "natural-language question, write exactly one SQLite SELECT statement "
        "that answers the question. Output only the SQL statement, nothing else."
    )

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #
    def _base_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Write the SQLite SELECT statement that answers this question. "
            "Output only the SQL statement."
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Your previous SQL attempt was:\n"
            f"{bad_sql}\n\n"
            "It failed to execute. SQLite returned this exact error:\n"
            f"{error}\n\n"
            "Write a corrected SQLite SELECT statement that answers the "
            "question and avoids this error. Output only the SQL statement."
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _generate(self, prompt: str) -> str:
        """Call the frozen solver and extract a clean SQL string from it."""
        text = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        sql = bridge.extract_sql(text)
        return sql.strip() if isinstance(sql, str) else ""

    def _safe_execute(self, sql: str) -> dict:
        """Run self.execute() defensively; never let the harness crash."""
        try:
            return self.execute(sql)
        except Exception as exc:  # pragma: no cover - defensive only
            return {"ok": False, "rows": [], "error": str(exc)}

    # ------------------------------------------------------------------ #
    # Main control flow
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # Round 0: initial generation from the question alone.
        sql = self._generate(self._base_prompt(question))

        # We get MAX_REPAIR_ROUNDS extra generations after failures,
        # i.e. up to 3 total generations and 3 executions.
        for attempt in range(self.MAX_REPAIR_ROUNDS + 1):
            result = self._safe_execute(sql)

            if result.get("ok"):
                # Execution succeeded: return the working SQL immediately.
                return sql

            # Repair budget exhausted: give up and return the last SQL.
            if attempt == self.MAX_REPAIR_ROUNDS:
                break

            # Feed the EXACT SQLite error back to the frozen solver and
            # regenerate, then loop to re-execute the new candidate.
            error = (result.get("error") or "unknown SQLite execution error").strip()
            sql = self._generate(self._repair_prompt(question, sql, error))

        # Final SQL string (possibly still broken, but the best we produced).
        return sql