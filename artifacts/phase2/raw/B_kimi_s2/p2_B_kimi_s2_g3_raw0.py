"""Repair-loop harness: generate SQL, execute it, and feed execution errors back into regeneration until the query runs."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G3(SQLHarness):
    """Wraps the frozen weak solver in a generate -> execute -> repair loop.

    Instead of trusting a single greedy generation, the harness executes the
    candidate SQL against the database. Whenever SQLite reports an error, the
    failing SQL together with the exact error message is appended to the
    prompt and the solver is asked to produce a corrected query. If the solver
    repeats an already-failed query verbatim, sampling temperature is raised
    for the next regeneration to escape the loop. The loop stops as soon as a
    query executes successfully, or after a bounded number of attempts, in
    which case the last candidate is returned as a best effort.
    """

    _SYSTEM = (
        "You are an expert SQLite text-to-SQL translator. Given a database "
        "schema and a natural-language question, output exactly one valid "
        "SQLite query. Output only the SQL query, with no explanations and "
        "no markdown prose."
    )

    _MAX_ATTEMPTS = 5
    _REPEAT_TEMPERATURE = 0.4

    def solve(self, question: str) -> str:
        # History of (sql, error) pairs that failed execution.
        failed_attempts = []

        sql = self._generate(question, failed_attempts, temperature=0.0)

        for attempt_idx in range(self._MAX_ATTEMPTS):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = (result.get("error") or "unknown execution error").strip()
            repeated = any(prev_sql == sql for prev_sql, _ in failed_attempts)
            failed_attempts.append((sql, error))

            if attempt_idx == self._MAX_ATTEMPTS - 1:
                break

            # If the solver is stuck on the same broken query, inject diversity.
            temperature = self._REPEAT_TEMPERATURE if repeated else 0.0
            sql = self._generate(question, failed_attempts, temperature=temperature)

        # Exhausted the repair budget: return the last candidate as best effort.
        return sql

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _generate(self, question: str, failed_attempts, temperature: float) -> str:
        prompt = self._build_prompt(question, failed_attempts)
        raw = self.llm(prompt, system=self._SYSTEM, temperature=temperature)
        sql = bridge.extract_sql(raw).strip()
        if not sql and failed_attempts:
            # Extraction failed entirely; keep the previous candidate rather
            # than returning an empty string.
            return failed_attempts[-1][0]
        return sql

    def _build_prompt(self, question: str, failed_attempts) -> str:
        parts = [
            "Database schema:",
            self.schema,
            "",
            "Question:",
            question,
        ]
        if failed_attempts:
            parts.append("")
            parts.append(
                "The following SQL queries were tried and FAILED to execute on "
                "this database. Read each SQLite error message carefully and "
                "produce a corrected query that avoids these mistakes. Do not "
                "repeat any of the failing queries."
            )
            for idx, (bad_sql, error) in enumerate(failed_attempts, start=1):
                parts.append("")
                parts.append(f"Failed attempt {idx} SQL:")
                parts.append(bad_sql)
                parts.append(f"Failed attempt {idx} SQLite error:")
                parts.append(error)
        parts.append("")
        if failed_attempts:
            parts.append(
                "Write a single corrected, executable SQLite query that answers "
                "the question."
            )
        else:
            parts.append(
                "Write a single executable SQLite query that answers the question."
            )
        return "\n".join(parts)