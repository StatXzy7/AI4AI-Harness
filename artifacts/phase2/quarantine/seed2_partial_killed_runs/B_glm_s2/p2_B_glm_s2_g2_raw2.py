"""Greedy text-to-SQL generation wrapped in an execution-repair loop: every candidate query is executed, and when the database rejects it the failing SQL and its error message are fed back to the frozen solver for up to three corrective regeneration rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2BGlmS2G2"]


class P2P2BGlmS2G2(SQLHarness):
    """Prompt-to-prompt harness over a frozen solver: greedy draft, then
    execution-error-driven repair rounds that re-query the LLM with the exact
    database error until the query executes or the repair budget is spent."""

    MAX_REPAIR_ROUNDS = 3
    MAX_SCHEMA_CHARS = 20000

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL engine working against a SQLite database. "
        "Use only the tables, columns, and literal values that appear in the given "
        "schema. Always reply with exactly one SQL SELECT statement and nothing "
        "else: no prose, no markdown fences, no comments, no explanation."
    )

    # ------------------------------------------------------------- public API

    def solve(self, question: str) -> str:
        candidate = self._draft(question)

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            outcome = self._run(candidate)
            if outcome["ok"]:
                return candidate
            if round_idx >= self.MAX_REPAIR_ROUNDS:
                break  # repair budget exhausted; return best effort
            repaired = self._repair(
                question, candidate, outcome["error"], round_idx
            )
            if repaired is None:
                break  # no usable / no different SQL produced: stop early
            candidate = repaired

        return candidate

    # ---------------------------------------------------------- control flow

    def _draft(self, question: str) -> str:
        prompt = (
            "Database schema:\n"
            f"{self._schema_block()}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. "
            "Respond with only the SQL statement."
        )
        return self._sql_from_llm(prompt)

    def _repair(self, question: str, broken_sql: str, error: str, round_idx: int):
        """Feed the failed SQL and the real database error back for regeneration."""
        prompt = (
            "Database schema:\n"
            f"{self._schema_block()}\n\n"
            f"Question: {question}\n\n"
            f"Your previous SQL attempt (repair round {round_idx + 1} of "
            f"{self.MAX_REPAIR_ROUNDS}) was:\n"
            f"{broken_sql or '(no SQL was produced)'}\n\n"
            "Executing it against the database failed with this error:\n"
            f"{error or '(no error message was provided)'}\n\n"
            "Diagnose the failure -- a misspelled table or column name, bad "
            "quoting, wrong join keys, an unsupported function, or invalid "
            "syntax -- and rewrite the query so it executes correctly while "
            "still answering the question. Respond with only the corrected "
            "SQL statement."
        )
        fixed = self._sql_from_llm(prompt)
        if not fixed:
            return None
        if fixed == (broken_sql or "").strip():
            return None  # identical output: further rounds would not progress
        return fixed

    # -------------------------------------------------------------- plumbing

    def _sql_from_llm(self, prompt: str) -> str:
        """Call the frozen solver and normalize its answer to bare SQL."""
        try:
            raw = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        except TypeError:
            # Fallback for executors with a narrower call signature.
            try:
                raw = self.llm(prompt)
            except Exception:
                return ""
        except Exception:
            return ""
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        if raw is None:
            return ""
        text = raw if isinstance(raw, str) else str(raw)
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            return ""
        return self._tidy(sql)

    @staticmethod
    def _tidy(sql) -> str:
        if not sql:
            return ""
        sql = str(sql).strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql.strip()

    def _schema_block(self) -> str:
        schema = str(getattr(self, "schema", None) or "").strip()
        if not schema:
            return "(no schema provided)"
        if len(schema) > self.MAX_SCHEMA_CHARS:
            schema = schema[: self.MAX_SCHEMA_CHARS] + "\n-- (schema truncated)"
        return schema

    def _run(self, sql: str) -> dict:
        """Execute a candidate defensively; never let executor faults crash solve."""
        if not sql:
            return {"ok": False, "rows": [], "error": "no SQL statement was produced"}
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": "executor raised: %s" % exc}
        if not isinstance(result, dict):
            return {
                "ok": False,
                "rows": [],
                "error": "executor returned a non-dict result",
            }
        ok = bool(result.get("ok"))
        error = str(result.get("error") or "").strip()
        if not ok and not error:
            error = "query failed to execute (no error message provided)"
        return {"ok": ok, "rows": result.get("rows") or [], "error": error}