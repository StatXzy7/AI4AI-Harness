"""A repair-loop Text-to-SQL harness: every generated query is executed, and execution errors are fed back to the LLM for bounded regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G1(SQLHarness):
    """Execution-feedback repair harness.

    Improvement over a single greedy generation: instead of returning the
    first query the frozen solver emits, this harness actually runs it
    against the database. Whenever execution fails, the failing SQL and the
    database's error message are appended to the prompt and the model is
    asked to regenerate, for up to MAX_ATTEMPTS total tries. The first query
    that executes successfully is returned; otherwise the most recent
    candidate is returned as a best-effort fallback.
    """

    MAX_ATTEMPTS = 4
    MAX_ERROR_CHARS = 800

    SYSTEM = (
        "You are an expert Text-to-SQL engine. Given a database schema and a "
        "natural-language question, output exactly one valid SQL query and "
        "nothing else."
    )

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _call_llm(self, prompt: str, temperature: float = 0.0) -> str:
        out = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. "
            "Output only the SQL, with no explanation or commentary."
        )

    def _repair_prompt(self, question: str, failures) -> str:
        prompt = self._initial_prompt(question)
        prompt += "\n\nThe following attempt(s) were executed and FAILED:\n"
        for idx, (bad_sql, error) in enumerate(failures, start=1):
            prompt += (
                f"\n--- Failed attempt {idx} ---\n"
                f"{bad_sql}\n"
                f"Database error: {error}\n"
            )
        prompt += (
            "\nDiagnose why these queries failed and write a corrected SQL "
            "query that will execute successfully. Output only the corrected "
            "SQL."
        )
        return prompt

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        failures = []  # (sql, error) pairs that did not execute successfully
        last_sql = ""

        for _ in range(self.MAX_ATTEMPTS):
            if failures:
                prompt = self._repair_prompt(question, failures)
            else:
                prompt = self._initial_prompt(question)

            raw = self._call_llm(prompt, temperature=0.0)
            sql = (bridge.extract_sql(raw) or "").strip()

            if not sql:
                failures.append(("<empty output>", "no SQL could be extracted"))
                continue

            # Greedy decoding can stubbornly repeat a known-bad query; if so,
            # spend one higher-temperature sample before executing it again.
            if any(sql == prev_sql for prev_sql, _ in failures):
                retry = self._call_llm(
                    prompt
                    + "\n\nAll queries above failed; propose a materially "
                      "different corrected query.",
                    temperature=0.6,
                )
                alt = (bridge.extract_sql(retry) or "").strip()
                if alt:
                    sql = alt

            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = str(result.get("error", "unknown execution error"))
            failures.append((sql, error[: self.MAX_ERROR_CHARS]))
            last_sql = sql

        # Best-effort fallback: return the most recent candidate even though
        # it never executed cleanly.
        return last_sql or "SELECT 1"