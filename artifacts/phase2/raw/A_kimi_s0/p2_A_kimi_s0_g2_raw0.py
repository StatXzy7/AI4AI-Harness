"""Generate SQL, execute it, and repair it by feeding database execution errors back to the LLM for regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G2(SQLHarness):
    """Text-to-SQL harness with an execution-feedback repair loop.

    Instead of returning the first greedy generation, this harness executes
    the candidate SQL and, on failure, re-prompts the model with the failed
    query and the database error message. The loop runs for at most
    MAX_ATTEMPTS rounds and returns the first query that executes
    successfully; otherwise it returns the last candidate as a best effort.
    """

    MAX_ATTEMPTS = 4

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL assistant. Given a database "
            "schema and a natural-language question, you write one correct "
            "SQL query. You output only the SQL query, with no commentary."
        )
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question."
        )

        prompt = base_prompt
        last_sql = ""
        last_error = ""

        for attempt in range(self.MAX_ATTEMPTS):
            # First attempt is greedy; retries get a little diversity so the
            # model can escape the mistake it just made.
            temperature = 0.0 if attempt == 0 else 0.3
            text = self.llm(prompt, system=system, temperature=temperature, n=1)
            if isinstance(text, list):
                text = text[0] if text else ""

            sql = bridge.extract_sql(text)
            if not sql:
                last_error = (
                    "No SQL statement could be extracted from your previous "
                    "response. Output exactly one SQL query."
                )
                prompt = self._repair_prompt(base_prompt, last_sql, last_error)
                continue

            last_sql = sql
            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive: treat harness errors as DB errors
                result = {"ok": False, "rows": [], "error": str(exc)}

            if result.get("ok"):
                return sql

            last_error = str(result.get("error", "unknown execution error"))
            prompt = self._repair_prompt(base_prompt, sql, last_error)

        # All attempts failed: return the most recent candidate as best effort.
        return last_sql or "SELECT 1"

    def _repair_prompt(self, base_prompt: str, failed_sql: str, error: str) -> str:
        error = error.strip() or "unknown error"
        if len(error) > 800:
            error = error[:800] + "..."
        failed_block = failed_sql.strip() or "(no SQL was produced)"
        return (
            f"{base_prompt}\n\n"
            "A previous attempt produced this SQL:\n"
            "