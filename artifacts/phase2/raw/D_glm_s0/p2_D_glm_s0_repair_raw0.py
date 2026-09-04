"""Generate SQL for a question, execute it against the database, and on failure feed the exact SQLite error back to the LLM to regenerate the query up to 2 times."""

from .. import bridge
from ..harness_base import SQLHarness


class P2P2DGlmS0Repair(SQLHarness):
    """Repair-loop harness around a frozen weak solver.

    Control flow (not just prompt wording) implements the strategy:
      1. Ask the LLM for a SQLite query given the schema + question.
      2. Execute the extracted SQL with ``self.execute``.
      3. If execution fails, build a new prompt containing the *exact* SQLite
         error string and the offending SQL, then regenerate.
      4. Repeat step 3 at most ``MAX_REPAIRS`` (2) times; return the last
         candidate as a best-effort answer if nothing ever executes cleanly.
    """

    MAX_REPAIRS = 2

    SYSTEM_PROMPT = (
        "You are an expert SQLite assistant. You are given a database schema "
        "and a natural-language question. Respond with exactly one valid "
        "SQLite query that answers the question. Output only the SQL "
        "statement: no explanations, no markdown fences, no extra text."
    )

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQLite query:"
        )

    def _repair_prompt(self, question: str, failed_sql: str, error: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "A previous attempt produced this SQLite query:\n"
            f"{failed_sql}\n\n"
            "Executing it against the database failed with this exact SQLite error:\n"
            f"{error}\n\n"
            "Rewrite the query so that it executes successfully against the "
            "schema above and still answers the question. Output only the "
            "corrected SQLite query."
        )

    # ------------------------------------------------------------------ #
    # Main solve loop
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        prompt = self._initial_prompt(question)

        last_sql = ""    # most recent non-empty SQL candidate
        last_error = ""  # most recent failure reason (exact SQLite error when available)

        # 1 initial generation + at most MAX_REPAIRS (2) regenerations.
        for attempt in range(self.MAX_REPAIRS + 1):
            response = self.llm(prompt, system=self.SYSTEM_PROMPT,
                                temperature=0.0, n=1)
            if isinstance(response, list):  # tolerate n-sample return shapes
                response = response[0] if response else ""

            candidate = bridge.extract_sql(response).strip()

            if candidate:
                last_sql = candidate
                try:
                    result = self.execute(candidate)
                except Exception as exc:  # defensive: never crash the harness
                    result = {"ok": False, "rows": [], "error": str(exc)}

                if result.get("ok"):
                    # Clean execution: return immediately.
                    return last_sql

                # Capture the EXACT SQLite error to feed back to the model.
                last_error = str(result.get("error") or "Unknown execution error.")
            else:
                # Nothing extractable: still counts as a failed attempt.
                last_error = ("No SQL statement could be extracted from the "
                              "previous model output.")

            # If repair rounds remain, rebuild the prompt with the failure info.
            if attempt < self.MAX_REPAIRS:
                shown_sql = last_sql if last_sql else "(no SQL produced)"
                prompt = self._repair_prompt(question, shown_sql, last_error)

        # Best effort: return the last candidate even if it never executed.
        return last_sql