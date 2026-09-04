"""Greedy text-to-SQL generation hardened by an execution-feedback repair loop that feeds each failing query and its real database error back to the model for up to three correction rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G2(SQLHarness):
    """Single greedy draft, then iterative repair driven by real execution errors.

    Control flow:

    1. Ask the model once (temperature 0) for a SQL answer to the question.
    2. Execute that SQL against the database.
    3. If it executes cleanly, return it immediately.
    4. Otherwise, show the model the schema, the question, the broken SQL and
       the exact database error message, and ask for a corrected query.
    5. Repeat (up to ``MAX_REPAIRS`` times), always keeping the most recent
       candidate. Stop early if a repaired query finally executes, or if the
       model starts echoing the same broken query (it is stuck).
    6. If nothing ever executes cleanly, return the latest attempt.
    """

    MAX_REPAIRS = 3

    # ------------------------------------------------------------ helpers

    def _generate(self, prompt: str, system: str) -> str:
        """One LLM call; tolerant of backends that return a 1-element list."""
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    def _extract(self, text: str) -> str:
        """Pull the SQL statement out of a model reply; never raises."""
        try:
            return bridge.extract_sql(text or "")
        except Exception:
            return (text or "").strip()

    def _run(self, sql: str):
        """Execute ``sql``; return (ok, error_message). Never raises."""
        if not sql or not sql.strip():
            return False, "No SQL statement was produced."
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: backend blowups are failures too
            return False, "Execution raised an exception: %s" % (exc,)
        if isinstance(result, dict) and result.get("ok"):
            return True, ""
        if isinstance(result, dict):
            err = str(result.get("error") or "")
            if err:
                return False, err
        return False, "The query failed to execute against the database."

    # ------------------------------------------------------------- solve

    def solve(self, question: str) -> str:
        schema = (self.schema or "").strip()

        base_system = (
            "You are an expert text-to-SQL engine. Given a database schema and a "
            "natural-language question, write exactly one SQLite query that answers "
            "the question. Use only tables and columns that appear in the schema. "
            "Reply with the SQL statement only: no explanation, no markdown fences."
        )
        ask = "Database schema:\n%s\n\nQuestion: %s\n\nSQL query:" % (schema, question)

        # ---- stage 1: initial greedy draft --------------------------------
        sql = self._extract(self._generate(ask, base_system))
        best_sql = sql
        ok, error = self._run(sql)
        if ok:
            return best_sql

        # ---- stage 2: execution-error-driven repair loop ------------------
        for _ in range(self.MAX_REPAIRS):
            repair_system = (
                base_system
                + " You previously produced a query that FAILED when it was executed "
                "on the real database. Use the reported error to diagnose the problem "
                "(misspelled table or column, syntax error, type mismatch, ...) and "
                "output a corrected query. Reply with the corrected SQL only."
            )
            repair_prompt = (
                "Database schema:\n%s\n\nQuestion: %s\n\n"
                "Previous SQL (it failed):\n%s\n\nDatabase error:\n%s\n\n"
                "Corrected SQL query:" % (schema, question, best_sql, error)
            )

            candidate = self._extract(self._generate(repair_prompt, repair_system))
            if not candidate or not candidate.strip():
                continue  # nothing extracted this round; try another repair
            if candidate.strip() == best_sql.strip():
                break  # model is echoing the same broken query; stop early

            ok, new_error = self._run(candidate)
            best_sql = candidate
            if ok:
                return best_sql
            error = new_error

        # No candidate ever executed cleanly; return the latest attempt.
        return best_sql