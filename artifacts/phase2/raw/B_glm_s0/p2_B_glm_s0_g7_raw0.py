"""Text-to-SQL harness that drafts a query greedily, executes it against the database, and feeds the resulting execution error back to the LLM for corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G7(SQLHarness):
    """Weak-solver wrapper with an execution-feedback repair loop.

    Control flow:
      1. Ask the frozen LLM for a SQL query (greedy, temperature 0).
      2. Execute the extracted SQL against the target database.
      3. If execution fails, re-prompt the LLM with the failing SQL plus
         the exact database error and ask for a corrected query.
      4. Repeat up to MAX_ATTEMPTS total generations. Return the first
         query that executes cleanly; if none do, return the most recent
         candidate so the caller still receives a SQL string.
    """

    MAX_ATTEMPTS = 3

    SYSTEM = (
        "You are an expert SQLite assistant. "
        "Answer with a single SQL SELECT statement and nothing else."
    )

    def solve(self, question: str) -> str:
        base_prompt = self._base_prompt(question)
        prompt = base_prompt
        last_sql = ""

        for _ in range(self.MAX_ATTEMPTS):
            # Greedy generation from the frozen solver.
            text = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
            sql = bridge.extract_sql(text)

            if not sql:
                # Nothing usable came back: ask for a clean regeneration.
                prompt = self._repair_prompt(
                    base_prompt,
                    previous_sql="(the previous answer contained no SQL)",
                    error="No SQL statement could be extracted from the response.",
                )
                continue

            last_sql = sql

            # Execute the candidate against the real database.
            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive: treat as an execution failure
                result = {"ok": False, "rows": [], "error": repr(exc)}

            if result.get("ok"):
                # Query executed successfully: accept it.
                return sql

            # Feed the database error back and ask for a corrected query.
            prompt = self._repair_prompt(
                base_prompt,
                previous_sql=sql,
                error=str(result.get("error") or "Unknown execution error"),
            )

        # Every attempt failed to execute; return the latest candidate anyway.
        return last_sql

    def _base_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite query that answers the question. "
            "Use only tables and columns that appear in the schema. "
            "Reply with the SQL inside a