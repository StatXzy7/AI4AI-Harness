"""Execution-feedback repair harness: generate SQL, execute it, and iteratively regenerate with the error message fed back into the prompt."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS1G2(SQLHarness):
    """Generate -> execute -> on failure, feed the DB error back and regenerate.

    Control flow: an initial greedy (temperature=0) generation is executed against
    the database. If execution fails, the failing SQL and the exact error message
    are appended to a running history, and the model is re-prompted (slightly
    higher temperature to escape the failure mode) to produce a corrected query.
    The loop stops at the first query that executes successfully, or after
    MAX_ATTEMPTS tries, in which case the most recent candidate is returned.
    """

    MAX_ATTEMPTS = 4

    SYSTEM = (
        "You are an expert SQLite text-to-SQL assistant. Given a database schema "
        "and a natural-language question, output exactly one valid SQLite query. "
        "Output only the SQL: no explanation, no comments, no markdown fences."
    )

    def _build_prompt(self, question: str, history: list) -> str:
        parts = [
            "Database schema:",
            self.schema,
            "",
            "Question: " + question,
        ]
        if history:
            parts += [
                "",
                "Previous attempt(s) FAILED to execute. Study the error(s) and write a corrected query.",
            ]
            for i, (bad_sql, err) in enumerate(history, 1):
                parts.append(f"--- Failed attempt {i} SQL ---")
                parts.append(bad_sql)
                parts.append(f"--- Database error {i} ---")
                parts.append(err)
            parts += [
                "",
                "Diagnose why the error occurred (wrong column/table names, bad joins, "
                "invalid SQLite syntax, etc.) and produce a fixed query. Change only "
                "what is needed to answer the question correctly.",
            ]
        parts += [
            "",
            "Write the SQL query now. Output only the SQL.",
        ]
        return "\n".join(parts)

    def _generate_sql(self, question: str, history: list, attempt: int) -> str:
        prompt = self._build_prompt(question, history)
        # Greedy first try; small temperature on retries so the model does not
        # deterministically repeat the same broken query.
        temperature = 0.0 if attempt == 0 else 0.3
        response = self.llm(prompt, system=self.SYSTEM, temperature=temperature)
        sql = bridge.extract_sql(response)
        if not sql:
            sql = (response or "").strip()
        return sql

    def solve(self, question: str) -> str:
        history = []
        last_sql = ""
        for attempt in range(self.MAX_ATTEMPTS):
            sql = self._generate_sql(question, history, attempt)
            if sql:
                last_sql = sql
            if not sql:
                history.append(("<empty generation>", "Model produced no SQL."))
                continue
            try:
                result = self.execute(sql)
            except Exception as exc:  # defensive: treat harness-level failure as DB error
                result = {"ok": False, "error": str(exc)}
            if result.get("ok"):
                return sql
            error = result.get("error") or "unknown execution error"
            history.append((sql, error))
        # All attempts failed: return the best candidate we have rather than nothing.
        return last_sql