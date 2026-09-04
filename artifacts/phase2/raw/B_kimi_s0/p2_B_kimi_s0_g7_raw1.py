"""A repair harness that executes candidate SQL and feeds execution errors (or empty results) back into bounded regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS0G7(SQLHarness):
    """Generate SQL, execute it, and iteratively repair it using execution feedback.

    Control flow:
      1. Greedy generation of an initial query.
      2. Execute the query.
         - Success with rows  -> return immediately.
         - Success, 0 rows    -> soft failure: keep as fallback, ask for a fix.
         - Execution error    -> hard failure: feed the error back.
      3. Regenerate with a repair prompt containing the full failure history.
      4. After MAX_ATTEMPTS, return the empty-but-valid fallback if one exists,
         otherwise return the last candidate.
    """

    MAX_ATTEMPTS = 4

    SYSTEM = (
        "You are an expert SQL writer for SQLite databases. "
        "Return exactly one SQL query and nothing else."
    )

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. "
            "Output only the SQL, no explanation."
        )

    def _repair_prompt(self, question: str, failures: list) -> str:
        lines = [
            "Database schema:",
            self.schema,
            "",
            f"Question: {question}",
            "",
            "The previous SQL attempt(s) did not produce a satisfactory result. "
            "Diagnose what went wrong and write a corrected query.",
            "",
        ]
        for i, (bad_sql, err) in enumerate(failures, 1):
            lines.append(f"--- Attempt {i} SQL ---")
            lines.append(bad_sql)
            lines.append(f"--- Attempt {i} feedback ---")
            lines.append(err)
            lines.append("")
        lines.append(
            "Write one corrected SQL query that resolves ALL of the feedback above. "
            "Check table names, column names, join keys, and filter values against "
            "the schema. Output only the SQL."
        )
        return "\n".join(lines)

    def _generate(self, prompt: str, temperature: float) -> str:
        text = self.llm(prompt, system=self.SYSTEM, temperature=temperature)
        sql = bridge.extract_sql(text)
        return sql.strip() if sql and sql.strip() else text.strip()

    def solve(self, question: str) -> str:
        failures = []
        empty_ok = None  # fallback: valid SQL that returned zero rows

        sql = self._generate(self._initial_prompt(question), temperature=0.0)

        for attempt in range(self.MAX_ATTEMPTS):
            if not sql:
                # Extraction produced nothing; regenerate from scratch.
                prompt = (
                    self._repair_prompt(question, failures)
                    if failures
                    else self._initial_prompt(question)
                )
                sql = self._generate(prompt, temperature=0.0)
                if not sql:
                    continue

            result = self.execute(sql)

            if result.get("ok"):
                rows = result.get("rows") or []
                if rows:
                    return sql
                if empty_ok is None:
                    empty_ok = sql
                failures.append(
                    (
                        sql,
                        "The query executed successfully but returned 0 rows. "
                        "An empty result is suspicious: re-check WHERE clause "
                        "values (exact spelling/casing), join conditions, and "
                        "whether the correct tables/columns were used.",
                    )
                )
            else:
                error = result.get("error") or "unknown execution error"
                failures.append((sql, f"Execution error: {error}"))

            temperature = min(0.2 * (attempt + 1), 0.6)
            sql = self._generate(
                self._repair_prompt(question, failures), temperature=temperature
            )

        # Prefer a syntactically valid, executable query over the last broken one.
        if empty_ok is not None:
            return empty_ok
        return sql