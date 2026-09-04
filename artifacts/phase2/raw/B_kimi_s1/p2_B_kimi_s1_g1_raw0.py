"""Repair-loop harness: generate SQL greedily, execute it, and feed any execution error back into the prompt for bounded regeneration."""
# MECHANISM: repair
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS1G1(SQLHarness):
    """Single greedy draft followed by an execution-feedback repair loop.

    Control flow:
      1. Draft SQL with one greedy (temperature=0.0) generation call.
      2. Execute the extracted SQL against the database.
      3. If execution succeeds, return that SQL immediately.
      4. If execution fails, build a repair prompt containing the bad SQL
         and the database's error message, then regenerate (slightly
         higher temperature for diversity) and loop.
      5. If the attempt budget is exhausted, return the first candidate
         that at least looked like SQL (best-effort fallback).
    """

    MAX_ATTEMPTS = 4

    SYSTEM = (
        "You are an expert Text-to-SQL translator. You output exactly one "
        "valid SQLite query and nothing else."
    )

    def _draft_prompt(self, question: str) -> str:
        return (
            "Convert the question into a single executable SQLite query.\n\n"
            "=== DATABASE SCHEMA ===\n"
            f"{self.schema}\n\n"
            "=== QUESTION ===\n"
            f"{question}\n\n"
            "=== RULES ===\n"
            "- Output ONLY the SQL. No explanation, no markdown fences.\n"
            "- Use only tables and columns that exist in the schema above.\n"
            "- Use a single SELECT statement; never modify the database.\n"
            "- Qualify columns with table names or aliases when joining.\n"
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str, attempt: int) -> str:
        return (
            "Your previous SQL query failed to execute. Fix it.\n\n"
            "=== DATABASE SCHEMA ===\n"
            f"{self.schema}\n\n"
            "=== QUESTION ===\n"
            f"{question}\n\n"
            "=== FAILED SQL (attempt " + str(attempt) + ") ===\n"
            f"{bad_sql}\n\n"
            "=== DATABASE ERROR ===\n"
            f"{error}\n\n"
            "=== RULES ===\n"
            "- Diagnose why the error occurred (e.g. wrong table/column name, "
            "bad join, syntax) and correct it.\n"
            "- Output ONLY the corrected SQL. No explanation, no markdown.\n"
            "- Use only tables and columns that exist in the schema above.\n"
        )

    def solve(self, question: str) -> str:
        prompt = self._draft_prompt(question)
        first_sql = ""
        last_sql = ""

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            # Greedy first draft; nudge temperature on repairs for diversity.
            temperature = 0.0 if attempt == 1 else 0.4
            text = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)

            sql = bridge.extract_sql(text)
            if not sql:
                sql = (text or "").strip().strip("`").strip()

            if not sql:
                # Model produced nothing usable; treat as an execution failure
                # and feed that fact back so the next attempt stays on task.
                prompt = self._repair_prompt(
                    question,
                    "(no SQL was produced)",
                    "No SQL statement was found in your previous response. "
                    "Output exactly one SQL query.",
                    attempt,
                )
                continue

            if not first_sql:
                first_sql = sql
            last_sql = sql

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error") or "unknown execution error"
            prompt = self._repair_prompt(question, sql, error, attempt)

        # Budget exhausted: prefer the earliest well-formed candidate.
        return first_sql or last_sql or "SELECT 1"