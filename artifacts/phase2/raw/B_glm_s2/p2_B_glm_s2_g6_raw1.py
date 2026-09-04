"""Execution-feedback repair loop: greedy SQL generation whose database errors are fed back to the frozen solver for up to three corrective regenerations."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G6(SQLHarness):
    """
    Improves on a single greedy call with an execute-then-repair loop:

    1. Ask the frozen solver for SQL (greedy, deterministic).
    2. Execute the SQL against the real database.
    3. If the database rejects it, re-prompt the solver with the schema,
       the question, the offending SQL, and the *exact* error message,
       asking for a corrected query.
    4. Repeat up to MAX_REPAIRS times; return the last candidate.
    """

    MAX_REPAIRS = 3

    SYSTEM = (
        "You are a careful SQLite expert. Translate the question into one "
        "single SQLite SELECT statement. Output only the SQL: no prose, no "
        "explanations, no markdown fences."
    )

    # ------------------------------------------------------------------ #
    # Prompt builders
    # ------------------------------------------------------------------ #
    def _first_prompt(self, question: str) -> str:
        return (
            "Database schema (SQLite):\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL query that answers the question.\n"
            "SQL:"
        )

    def _repair_prompt(self, question: str, bad_sql: str, error: str) -> str:
        return (
            "Database schema (SQLite):\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "A first attempt at the SQL was:\n"
            f"{bad_sql}\n\n"
            "Executing it against the database failed with this error:\n"
            f"{error}\n\n"
            "Rewrite the query so that it executes correctly. Re-check every "
            "table and column name against the schema above, fix quoting, "
            "joins, and aggregates as needed.\n"
            "Output only the corrected SQL statement."
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _as_text(out) -> str:
        """Defensive: some LLM wrappers return a list even for n=1."""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return "" if out is None else str(out)

    @staticmethod
    def _normalize(sql) -> str:
        """Light cleanup: trim whitespace and trailing semicolons."""
        if not sql:
            return ""
        sql = str(sql).strip()
        while sql.endswith(";"):
            sql = sql[:-1].strip()
        return sql

    def _extract(self, raw) -> str:
        try:
            return self._normalize(bridge.extract_sql(self._as_text(raw)))
        except Exception:
            return ""

    def _error_of(self, sql: str):
        """Execute *sql*; return None on success, otherwise an error message."""
        if not sql:
            return "no SQL statement was produced"
        if not sql.upper().startswith(("SELECT", "WITH")):
            return ("the statement is not a read-only query "
                    "(only SELECT / WITH queries are allowed)")
        try:
            result = self.execute(sql)
        except Exception as exc:  # executor itself blew up
            return f"executor raised: {exc}"
        if not isinstance(result, dict):
            return "executor returned an unexpected result"
        if not result.get("ok"):
            return str(result.get("error") or "unknown execution error")
        return None

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # --- stage 1: plain greedy first shot from the frozen solver ---- #
        raw = self.llm(
            self._first_prompt(question),
            system=self.SYSTEM,
            temperature=0.0,
            n=1,
        )
        sql = self._extract(raw)

        # --- stage 2: execute, and repair on failure -------------------- #
        error = self._error_of(sql)
        repairs = 0
        while error is not None and repairs < self.MAX_REPAIRS:
            raw = self.llm(
                self._repair_prompt(question, sql, error),
                system=self.SYSTEM,
                temperature=0.0,
                n=1,
            )
            candidate = self._extract(raw)
            repairs += 1
            if not candidate or candidate == sql:
                # Solver gave up or repeated itself verbatim -> stop early.
                break
            sql = candidate
            error = self._error_of(sql)

        # --- return the last (possibly still failing) candidate --------- #
        return sql