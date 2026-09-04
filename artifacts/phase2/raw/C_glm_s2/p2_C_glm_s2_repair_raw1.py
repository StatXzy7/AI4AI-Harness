"""Generate a candidate SQLite query, execute it against the database, and on failure feed the exact SQLite error back to the model to regenerate a corrected query, retrying up to 2 times."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS2Repair(SQLHarness):
    """Weak-solver wrapper: generate -> execute -> repair-with-exact-SQLite-error (max 2 repairs)."""

    #: Number of regeneration rounds allowed after the first failed execution.
    MAX_REPAIRS = 2

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL agent. "
        "You answer questions by writing a single, executable SQLite SELECT query."
    )

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema (SQLite):\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write ONE SQLite SQL query that answers the question above.\n"
            "Constraints:\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Output a single SELECT statement.\n"
            "- Output ONLY the SQL; no explanation, no commentary.\n"
        )

    def _repair_prompt(self, question: str, failed_sql: str, error: str) -> str:
        return (
            "Database schema (SQLite):\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Your previous query was:\n"
            f"{failed_sql}\n\n"
            "Executing it in SQLite failed with this exact error:\n"
            f"{error}\n\n"
            "Rewrite the query so it executes successfully against the schema.\n"
            "Constraints:\n"
            "- Fix the specific cause of the error quoted above.\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Output a single SELECT statement.\n"
            "- Output ONLY the SQL; no explanation, no commentary.\n"
        )

    # ------------------------------------------------------------------ #
    # Execution helpers
    # ------------------------------------------------------------------ #

    def _run_sql(self, sql: str) -> dict:
        """Execute SQL defensively; unexpected exceptions become failure dicts."""
        try:
            return self.execute(sql)
        except Exception as exc:  # defensive: treat crashes as execution failures
            return {"ok": False, "rows": [], "error": f"execution raised: {exc}"}

    # ------------------------------------------------------------------ #
    # Main control flow
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        sql = ""
        last_error = "Error: no SQL statement was produced."

        # attempt 0 = initial generation; attempts 1..MAX_REPAIRS = error-feedback repairs
        for attempt in range(1 + self.MAX_REPAIRS):
            if attempt == 0:
                prompt = self._initial_prompt(question)
            else:
                # Repair round: the exact SQLite error from the previous round is
                # quoted verbatim so the model can fix its specific cause.
                prompt = self._repair_prompt(question, sql, last_error)

            raw = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
            sql = bridge.extract_sql(raw)

            # No extractable SQL counts as a failure and triggers a repair round.
            if not sql or not sql.strip():
                last_error = "Error: the model output contained no SQL statement."
                continue

            result = self._run_sql(sql)

            if result.get("ok"):
                return sql

            # Feed the exact SQLite error back for the next regeneration round.
            last_error = str(result.get("error") or "Unknown SQLite execution error.")

        # All attempts failed: return the last generated SQL as the final answer.
        return sql