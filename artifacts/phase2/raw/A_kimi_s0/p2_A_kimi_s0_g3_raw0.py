"""Repair harness: generate SQL greedily, execute it, and feed any execution error back to the frozen LLM so it regenerates a corrected query."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G3(SQLHarness):
    """Text-to-SQL harness using execution-feedback repair.

    Instead of trusting a single greedy generation, the harness executes the
    candidate SQL against the database. Whenever execution fails, the failing
    SQL and the database's error message are appended to the prompt and the
    frozen solver is asked to produce a corrected query. This repair loop runs
    for a bounded number of attempts, with a small temperature escalation on
    later retries so a weak deterministic solver can escape repeated mistakes.
    The first successfully executing query is returned; if none succeeds, the
    best-effort candidate is returned rather than nothing.
    """

    MAX_ATTEMPTS = 4
    TEMPERATURES = (0.0, 0.2, 0.5, 0.7)
    MAX_ERROR_CHARS = 600

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL translator. Given a database schema and "
        "a natural-language question, you output exactly one SQL query that "
        "answers the question. Use only tables and columns that appear in the "
        "schema. Output the SQL only, with no explanation."
    )

    def solve(self, question: str) -> str:
        best_sql = ""
        last_raw = ""
        previous_sql = ""
        previous_error = ""

        for attempt in range(self.MAX_ATTEMPTS):
            if attempt == 0:
                prompt = self._initial_prompt(question)
            else:
                prompt = self._repair_prompt(question, previous_sql, previous_error)

            temperature = self.TEMPERATURES[min(attempt, len(self.TEMPERATURES) - 1)]
            raw = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=temperature, n=1)
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""
            raw = raw or ""
            last_raw = raw

            sql = bridge.extract_sql(raw) or ""
            if not sql.strip():
                previous_sql = raw.strip() or "(empty response)"
                previous_error = (
                    "Your response did not contain an extractable SQL statement. "
                    "Respond with only the SQL query."
                )
                continue

            best_sql = sql
            result = self._safe_execute(sql)
            if result["ok"]:
                return sql

            previous_sql = sql
            previous_error = result["error"]

        return best_sql or last_raw.strip()

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. Output the SQL only."
        )

    def _repair_prompt(self, question: str, previous_sql: str, previous_error: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Your previous SQL query failed to execute on this database.\n"
            "Previous SQL:\n"
            f"{previous_sql}\n\n"
            "Database error:\n"
            f"{previous_error}\n\n"
            "Diagnose the error and write a corrected SQL query. Check table and "
            "column names against the schema exactly (including quoting and join "
            "conditions). Output the corrected SQL only."
        )

    def _safe_execute(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
        except Exception as exc:  # treat harness-side failures as SQL errors too
            return {"ok": False, "error": f"execution raised {type(exc).__name__}: {exc}"}
        ok = bool(result.get("ok"))
        error = "" if ok else str(result.get("error", "unknown execution error"))
        if len(error) > self.MAX_ERROR_CHARS:
            error = error[: self.MAX_ERROR_CHARS] + "..."
        return {"ok": ok, "error": error}