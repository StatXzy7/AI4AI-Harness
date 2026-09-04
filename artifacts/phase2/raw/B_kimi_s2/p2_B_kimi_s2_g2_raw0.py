"""Execution-feedback repair harness: generate SQL greedily, execute it, and feed any database error back to the LLM for correction, repeating until success or budget exhaustion."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G2(SQLHarness):
    """Text-to-SQL harness with an execution-driven repair loop.

    Control flow:
      1. The frozen LLM greedily produces a candidate SQL query.
      2. The harness executes the candidate against the database.
      3. If execution succeeds, the SQL is returned immediately.
      4. If execution fails, the failing SQL and the database error message
         are fed back into a repair prompt, and the LLM regenerates a
         corrected query. This repeats up to MAX_REPAIRS times.
      5. If the repair loop plateaus (identical SQL regenerated) or the
         budget is exhausted, the most recent candidate is returned as the
         best-effort answer.
    """

    MAX_REPAIRS = 3

    SYSTEM_PROMPT = (
        "You are an expert SQLite developer. Translate the user's natural "
        "language question into a single valid SQL query for the given "
        "schema. Output ONLY the SQL query, with no explanations or prose."
    )

    def _initial_prompt(self, question: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question."
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "The following SQL query was generated to answer the question:\n"
            f"{bad_sql}\n\n"
            f"Executing it against the database failed with this error:\n{error}\n\n"
            "Diagnose the cause of the error (check table names, column names, "
            "join conditions, and syntax against the schema) and rewrite the "
            "query so that it executes correctly while still answering the "
            "original question. Output ONLY the corrected SQL query."
        )

    def _generate_sql(self, prompt: str, temperature: float = 0.0) -> str:
        text = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=temperature)
        return bridge.extract_sql(text)

    def solve(self, question: str) -> str:
        # Step 1: initial greedy generation.
        sql = self._generate_sql(self._initial_prompt(question))
        if not sql:
            # Extraction failed; retry once with sampling to get usable text.
            sql = self._generate_sql(self._initial_prompt(question), temperature=0.5)
        if not sql:
            return ""

        # Steps 2-4: execute-and-repair loop.
        for _ in range(self.MAX_REPAIRS):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error") or "unknown execution error"
            repaired = self._generate_sql(self._repair_prompt(question, sql, error))

            if not repaired or repaired.strip() == sql.strip():
                # Repair plateau: escape with a non-zero-temperature retry.
                repaired = self._generate_sql(
                    self._repair_prompt(question, sql, error), temperature=0.4
                )
                if not repaired or repaired.strip() == sql.strip():
                    break

            sql = repaired

        # Step 5: budget exhausted or plateau; return best-effort candidate.
        return sql