"""Execution-feedback repair loop: generate SQL, run it, and feed errors or empty results back into the prompt for regeneration until success or budget exhaustion."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G5(SQLHarness):
    """Text-to-SQL harness that repairs its SQL by observing real execution results.

    Control flow:
      1. Greedy generation of an initial SQL query.
      2. Execute it against the database.
      3. If it errors (or returns zero rows), append the failure signal to a
         feedback transcript and regenerate with that transcript in context.
      4. Repeat up to MAX_ATTEMPTS; keep the best executable SQL as fallback.
    """

    MAX_ATTEMPTS = 4
    FEEDBACK_WINDOW = 2  # only the most recent failures are re-fed, keeping prompts bounded

    def _generate(self, prompt: str, system: str) -> str:
        """Call the frozen LLM and normalize its return type to a plain string."""
        text = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        return str(text)

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL engine. "
            "Given a database schema and a natural-language question, you output "
            "exactly one valid SQLite query. Output only the SQL: no prose, no "
            "markdown fences, no comments."
        )
        base_prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite query that answers the question."
        )

        feedback = []        # list of failure transcripts
        last_sql = ""        # most recent candidate
        executable_sql = ""  # first candidate that ran without error

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            if feedback:
                history = "\n\n".join(feedback[-self.FEEDBACK_WINDOW:])
                prompt = (
                    f"{base_prompt}\n\n"
                    "Your previous attempt(s) failed. Diagnose the failure and "
                    "produce a corrected query.\n\n"
                    f"{history}\n\n"
                    "Output only the corrected SQL query."
                )
            else:
                prompt = base_prompt

            sql = bridge.extract_sql(self._generate(prompt, system))

            if not sql:
                feedback.append(
                    f"[Attempt {attempt}] No SQL could be extracted from your "
                    "output. Respond with a single SQL statement only."
                )
                continue

            last_sql = sql
            result = self.execute(sql)

            if result.get("ok"):
                if not executable_sql:
                    executable_sql = sql
                if result.get("rows"):
                    # Executed and non-empty: accept immediately.
                    return sql
                feedback.append(
                    f"[Attempt {attempt}] This query executed but returned ZERO rows:\n"
                    f"{sql}\n"
                    "Likely causes: a filter value that does not match the stored "
                    "data exactly, an over-restrictive JOIN, or a wrong column. "
                    "Re-check literal values against the schema, prefer LIKE for "
                    "uncertain string matches, and relax unneeded predicates."
                )
            else:
                feedback.append(
                    f"[Attempt {attempt}] This query failed to execute.\n"
                    f"SQL:\n{sql}\n"
                    f"Database error: {result.get('error', 'unknown error')}\n"
                    "Fix the syntax/identifier problem and return a runnable query."
                )

        # Budget exhausted: prefer any SQL that at least executed cleanly.
        if executable_sql:
            return executable_sql
        return last_sql or "SELECT 1"