"""Repair harness: generate SQL greedily, execute it, and feed execution errors back into the prompt for bounded regeneration."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS1G6(SQLHarness):
    """Text-to-SQL harness with an execution-feedback repair loop.

    Improvement over a single greedy call: instead of returning the first
    generated query, we actually run it against the database. If execution
    fails, the failing SQL and its error message are appended to the prompt
    and the model is asked to produce a corrected query. This repeats for a
    bounded number of attempts; the first query that executes successfully
    is returned. If every attempt fails, the most recent candidate is
    returned as a fallback.
    """

    MAX_ATTEMPTS = 4

    SYSTEM = (
        "You are an expert SQLite text-to-SQL translator. Given a database "
        "schema and a natural-language question, output exactly one valid "
        "SQLite query that answers the question. Output only the SQL query, "
        "with no explanation and no markdown fences."
    )

    def solve(self, question: str) -> str:
        base_prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQLite SQL query that answers the question."
        )

        failures = []  # list of (sql_text, error_message) from prior attempts

        for attempt in range(self.MAX_ATTEMPTS):
            prompt = self._build_prompt(base_prompt, failures)
            sql = self._generate(prompt)

            if not sql:
                failures.append(
                    ("<no SQL extracted>", "model output contained no SQL query")
                )
                continue

            result = self._run(sql)
            if result.get("ok"):
                # Executed successfully: this is our final answer.
                return sql

            error = result.get("error") or "unknown execution error"
            failures.append((sql, error))

        # All repair attempts exhausted: fall back to the last candidate SQL
        # (better to return a plausible query than nothing at all).
        for sql_text, _ in reversed(failures):
            if sql_text and sql_text != "<no SQL extracted>":
                return sql_text
        return "SELECT 1"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, base_prompt: str, failures) -> str:
        """First attempt uses the plain prompt; later attempts include the
        failing SQL and its execution error so the model can repair it."""
        if not failures:
            return base_prompt

        parts = [base_prompt, "", "Previous attempts failed to execute:"]
        for i, (sql_text, error) in enumerate(failures, 1):
            parts.append(
                f"--- Attempt {i} ---\n{sql_text}\nExecution error: {error}"
            )
        parts.append(
            "\nAnalyze why the previous query failed, then rewrite it so it "
            "executes successfully on the given schema and answers the "
            "question. Output only the corrected SQL query."
        )
        return "\n".join(parts)

    def _generate(self, prompt: str) -> str:
        """Call the frozen solver greedily and extract SQL from its output."""
        try:
            raw = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        except TypeError:
            # In case the underlying solver does not accept n=
            raw = self.llm(prompt, system=self.SYSTEM, temperature=0.0)
        except Exception:
            return ""

        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        if raw is None:
            return ""

        sql = bridge.extract_sql(str(raw))
        return (sql or "").strip()

    def _run(self, sql: str) -> dict:
        """Execute SQL defensively, converting exceptions into error dicts."""
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: treat crashes as failures
            return {"ok": False, "rows": [], "error": f"exception: {exc}"}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "execute returned non-dict"}
        return result