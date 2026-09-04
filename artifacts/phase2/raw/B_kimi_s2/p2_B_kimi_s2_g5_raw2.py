"""Text-to-SQL harness that iteratively repairs SQL by executing each candidate and feeding database errors back to the LLM for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G5(SQLHarness):
    """Generate-execute-repair loop.

    Instead of trusting a single greedy generation, each candidate query is
    executed against the database. Whenever execution fails, the exact error
    message and the offending SQL are appended to the prompt and the model is
    asked to produce a corrected query. The loop stops at the first query that
    executes successfully; otherwise the last syntactically extractable query
    is returned as a best effort.
    """

    MAX_ATTEMPTS = 5

    SYSTEM = (
        "You are an expert Text-to-SQL engine. Given a database schema and a "
        "natural-language question, you write exactly one valid SQLite SELECT "
        "query. You output only the SQL query itself: no prose, no markdown "
        "fences, no commentary."
    )

    def solve(self, question: str) -> str:
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SELECT query that answers the question."
        )

        prompt = base_prompt
        best_sql = ""

        for attempt in range(self.MAX_ATTEMPTS):
            # First try is fully greedy; retries get a little temperature so a
            # repeated failure mode can be escaped even with similar feedback.
            temperature = 0.0 if attempt == 0 else min(0.2 * attempt, 0.6)

            raw = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""

            sql = bridge.extract_sql(raw)

            if not sql:
                # Model failed to emit anything parseable: treat that as a
                # repairable failure and feed it back just like a DB error.
                prompt = self._repair_prompt(
                    base_prompt,
                    best_sql or "(no SQL was produced)",
                    "Your previous reply contained no extractable SQL query. "
                    "Respond with the query text only.",
                )
                continue

            best_sql = sql
            result = self.execute(sql)

            if result.get("ok"):
                return sql

            error = str(result.get("error", "unknown database error"))[:500]
            prompt = self._repair_prompt(base_prompt, sql, error)

        # All repair attempts exhausted: return the best query we managed to
        # extract rather than crashing or returning prose.
        return best_sql if best_sql else "SELECT 1"

    def _repair_prompt(self, base_prompt: str, bad_sql: str, error: str) -> str:
        return (
            f"{base_prompt}\n\n"
            "---- FEEDBACK FROM THE DATABASE ----\n"
            "The following SQL query was tried:\n"
            f"{bad_sql}\n\n"
            f"It failed with this error:\n{error}\n\n"
            "Diagnose the cause (wrong table or column names, bad joins, "
            "invalid syntax, type mismatches, ambiguous columns, etc.) and "
            "output one corrected SQLite SELECT query. Output only the "
            "corrected SQL, nothing else."
        )