"""Repair-loop Text-to-SQL harness: generate a candidate SQL query, execute it against the database, and on failure re-prompt the model with the exact SQLite error to regenerate a corrected query up to two times."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS1Repair(SQLHarness):
    """Weak-solver wrapper implementing a generate -> execute -> repair loop.

    Control flow (not just prompting) drives the repair:
      1. Ask the model for a SQL query given the schema and question.
      2. Execute the extracted query via ``self.execute``.
      3. If SQLite reports an error, build a new prompt containing the failed
         query and the *exact* error text, and regenerate.
      4. Repeat at most ``MAX_REPAIRS`` times (3 generations total).
      5. Return the first query that executes cleanly; otherwise return the
         most recent non-empty candidate.
    """

    MAX_REPAIRS = 2
    SYSTEM = "You are an expert SQLite query writer."

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite query that answers the question. "
            "Respond with only the SQL query and no explanation."
        )

    def _repair_prompt(self, question: str, failed_sql: str, error: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Your previous SQL query was:\n"
            f"{failed_sql}\n\n"
            "Executing it in SQLite produced this exact error:\n"
            f"{error}\n\n"
            "Rewrite the query so it executes successfully against the schema "
            "and still answers the question. Respond with only the corrected "
            "SQL query and no explanation."
        )

    def _generate(self, prompt: str) -> str:
        text = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        return bridge.extract_sql(text or "")

    def solve(self, question: str) -> str:
        sql = ""
        error = "no SQL was produced"

        # 1 initial generation + up to MAX_REPAIRS repair generations.
        for attempt in range(1 + self.MAX_REPAIRS):
            if attempt == 0:
                prompt = self._initial_prompt(question)
            else:
                # Repair round: feed back the failed SQL and the exact error.
                prompt = self._repair_prompt(question, sql, error)

            candidate = self._generate(prompt)
            if not candidate:
                # Nothing extractable: force another round with a clear reason.
                error = (
                    "Error: the previous response contained no SQL statement; "
                    "output a SQL statement."
                )
                continue

            sql = candidate
            result = self.execute(sql)

            if isinstance(result, dict) and result.get("ok"):
                return sql  # Query executed successfully.

            error = (
                (result.get("error") if isinstance(result, dict) else "")
                or "unknown execution error"
            )

        # Every attempt failed; return the last viable SQL as-is.
        return sql