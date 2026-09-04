"""Execute the generated SQL and, when SQLite reports an error, feed the failing query and the verbatim error back to the solver for up to two corrective regenerations."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G1(SQLHarness):
    """Greedy generation plus an execution-feedback repair loop.

    Control flow:
      1. Ask the frozen solver for one SQL query (question + schema).
      2. Execute the query against the database.
      3. If execution succeeds, return it immediately.
      4. If execution fails, build a repair prompt containing the failed SQL
         and the exact SQLite error message, and ask the solver to regenerate
         a corrected query.  Go back to step 2.
      5. Stop after ``MAX_REPAIRS`` repair rounds (or if the solver starts
         repeating a query that already failed) and return the last candidate.
    """

    MAX_REPAIRS = 2

    SYSTEM = (
        "You are an expert SQLite text-to-SQL translator. "
        "Reply with exactly one SQL query, nothing else."
    )

    def solve(self, question: str) -> str:
        prompt = self._initial_prompt(question)
        last_sql = ""
        tried = set()

        for _ in range(1 + self.MAX_REPAIRS):
            # --- generation stage (frozen solver) -----------------------
            raw = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
            sql = self._clean(bridge.extract_sql(self._as_text(raw)))

            # --- execution / verification stage -------------------------
            if sql:
                last_sql = sql
                result = self._run(sql)
                if result.get("ok"):
                    return sql
                error = result.get("error") or "Execution failed for an unknown reason."
            else:
                error = "No SQL statement was found in the model output."

            # No progress if the solver repeats an already-failed query.
            if sql in tried:
                break
            tried.add(sql)

            # --- repair prompt: failed SQL + verbatim error --------------
            prompt = self._repair_prompt(question, sql, error)

        # Best effort: nothing executed cleanly, return the last candidate.
        return last_sql

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema or ''}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SQL query that answers the question.\n"
            "Output only the query inside one