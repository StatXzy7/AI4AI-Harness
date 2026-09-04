"""Self-repairing text-to-SQL harness that executes each candidate query and feeds database error messages back to the LLM for corrective regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G2(SQLHarness):
    """Greedy generation plus an execution-error-driven repair loop.

    Control flow (a real change over a single greedy call):

      1. Ask the LLM for one SQL query (greedy, temperature 0).
      2. Execute that query against the database.
      3. If execution fails, re-prompt the LLM showing the failing SQL and
         the actual database error string, and ask for a corrected query.
      4. Repeat up to MAX_ATTEMPTS times (with slightly raised temperature on
         retries so the model can escape a deterministic failure mode).
      5. Return the first query that executes cleanly; if none does, return
         the most recent candidate.
    """

    MAX_ATTEMPTS = 3
    MAX_ERROR_CHARS = 500

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "natural-language question, output exactly one SQLite SELECT statement. "
        "Output only the SQL statement itself: no explanation, no markdown."
    )

    def solve(self, question: str) -> str:
        base_prompt = (
            "Schema:\n%s\n\nQuestion: %s\n\n"
            "Write a single SQL query that answers the question."
            % (self.schema, question)
        )

        last_sql = ""
        last_error = ""
        tried = set()

        for attempt in range(self.MAX_ATTEMPTS):
            if attempt == 0:
                prompt = base_prompt
                temperature = 0.0
            else:
                prompt = self._repair_prompt(question, last_sql, last_error)
                # Diversify retries slightly so a deterministically broken
                # answer does not simply repeat itself.
                temperature = 0.2 * attempt

            text = self.llm(
                prompt,
                system=self.SYSTEM_PROMPT,
                temperature=temperature,
                n=1,
            )
            sql = bridge.extract_sql(text).strip()

            if not sql:
                # Nothing parseable came back; treat as a repairable failure.
                last_sql = ""
                last_error = "no recognizable SQL statement was produced"
                continue

            if sql in tried:
                # Identical query already proven broken; skip re-executing it
                # and ask again with a fresh sample.
                continue
            tried.add(sql)

            result = self.execute(sql) or {}
            if result.get("ok"):
                return sql

            last_sql = sql
            last_error = str(
                result.get("error") or "unknown execution error"
            ).strip()[: self.MAX_ERROR_CHARS]

        # Every attempt failed to execute; return the last candidate we have.
        return last_sql

    def _repair_prompt(self, question: str, failed_sql: str, error: str) -> str:
        if failed_sql:
            previous_block = "Previous attempt:\n%s" % failed_sql
        else:
            previous_block = "Previous attempt: (no SQL statement was produced)"

        return (
            "Schema:\n%s\n\n"
            "Question: %s\n\n"
            "%s\n\n"
            "It failed to execute against the database with this error:\n%s\n\n"
            "Rewrite the query so that it executes successfully against the "
            "schema and still answers the question. Pay attention to table and "
            "column names. Output only the corrected SQL statement."
            % (self.schema, question, previous_block, error)
        )