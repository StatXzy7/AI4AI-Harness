"""A bounded repair loop: generate SQL, execute it, and feed any database error back into the next generation until it runs or attempts run out."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS1G0(SQLHarness):
    """Text-to-SQL harness with an execution-feedback repair loop.

    Instead of trusting the first greedy generation, this harness executes the
    candidate SQL against the database. Whenever execution fails, the failing
    SQL and the exact database error are appended to a repair transcript that
    is fed back to the frozen solver, which is asked to rewrite the query.
    Later attempts use a slightly higher temperature so the solver can escape
    the mistake it committed greedily. The loop stops at the first query that
    executes successfully, or after MAX_ATTEMPTS tries, in which case the last
    candidate is returned as a best effort.
    """

    MAX_ATTEMPTS = 4
    # Greedy first try; mild exploration on subsequent repairs.
    TEMPERATURES = (0.0, 0.2, 0.4, 0.6)

    SYSTEM = (
        "You are an expert SQLite text-to-SQL engine. Given a database schema "
        "and a natural-language question, write exactly one valid SQLite "
        "SELECT query that answers the question. Output only the SQL query, "
        "with no explanation, no commentary, and no markdown formatting."
    )

    def _base_prompt(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        return (
            "Database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SELECT query that answers the question."
        )

    def _repair_prompt(self, question: str, failures: list) -> str:
        prompt = self._base_prompt(question)
        prompt += (
            "\n\nYour previous attempt(s) failed to execute. "
            "Here is the history of what went wrong:\n"
        )
        for i, (bad_sql, error) in enumerate(failures, start=1):
            prompt += (
                f"\nAttempt {i} SQL:\n{bad_sql}\n"
                f"Attempt {i} database error:\n{error}\n"
            )
        prompt += (
            "\nAnalyze why the query failed (check table names, column names, "
            "join conditions, and SQLite syntax) and output a corrected single "
            "SQLite SELECT query. Output only the corrected SQL."
        )
        return prompt

    def _generate(self, prompt: str, temperature: float) -> str:
        """Call the frozen solver and normalize its output to a plain string."""
        raw = self.llm(
            prompt,
            system=self.SYSTEM,
            temperature=temperature,
            n=1,
        )
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        return raw if isinstance(raw, str) else str(raw)

    def _try_execute(self, sql: str):
        """Execute SQL, converting raised exceptions into error dicts."""
        try:
            return self.execute(sql)
        except Exception as exc:  # defensive: treat crashes as execution errors
            return {"ok": False, "rows": [], "error": f"{type(exc).__name__}: {exc}"}

    def solve(self, question: str) -> str:
        failures = []          # [(sql, error), ...] repair transcript
        last_sql = ""          # best-effort fallback if nothing ever succeeds

        for attempt in range(self.MAX_ATTEMPTS):
            temperature = self.TEMPERATURES[
                min(attempt, len(self.TEMPERATURES) - 1)
            ]
            if failures:
                prompt = self._repair_prompt(question, failures)
            else:
                prompt = self._base_prompt(question)

            raw_text = self._generate(prompt, temperature)
            sql = bridge.extract_sql(raw_text)

            if not sql:
                # Nothing parseable came back: record a synthetic failure so
                # the next repair round explicitly demands bare SQL.
                failures.append(
                    (
                        "(no SQL could be extracted from the model output)",
                        "Output contained no SQL query. Respond with only the "
                        "SQL text, no prose or markdown.",
                    )
                )
                continue

            last_sql = sql
            result = self._try_execute(sql)

            if result.get("ok"):
                return sql

            error = (result.get("error") or "unknown execution error").strip()
            failures.append((sql, error))

        # All attempts failed: return the most recent candidate rather than
        # nothing, so downstream consumers still receive a SQL string.
        return last_sql if last_sql else "SELECT 1"