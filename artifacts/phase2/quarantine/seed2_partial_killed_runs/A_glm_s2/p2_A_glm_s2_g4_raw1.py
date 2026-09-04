"""Iterative repair: the greedy SQL answer is executed against the database, and every execution error is fed back into the prompt for corrective regeneration, for up to three repair rounds, until a query executes cleanly."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G4(SQLHarness):
    """Greedy text-to-SQL wrapped in an execution-error feedback repair loop.

    Control flow of :meth:`solve`:

    1. One greedy LLM call turns ``(schema, question)`` into a candidate SQL
       statement.
    2. The candidate is executed against the real database.
    3. If execution fails -- or no SQL could even be extracted from the model
       output -- the failed query and the database error message are put into
       a repair prompt and the LLM regenerates the query.
    4. Steps 2-3 repeat for at most ``max_repair_rounds`` rounds; the first
       query that executes successfully is returned immediately.  If nothing
       ever executes, the model's original direct answer is returned.
    """

    #: number of corrective regeneration rounds after the initial generation
    max_repair_rounds = 3
    #: maximum characters of an error message echoed back into a prompt
    max_error_chars = 600

    system_prompt = (
        "You are an expert text-to-SQL engine. You reply with exactly one "
        "SQLite SELECT statement and nothing else - no prose, no markdown, "
        "no code fences."
    )

    # ------------------------------------------------------------------ #
    # prompt construction
    # ------------------------------------------------------------------ #

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "{schema}\n\n"
            "Question: {question}\n\n"
            "Write one SQLite query that answers the question.\n"
            "Use only tables and columns that appear in the schema.\n"
            "Output only the SQL query.\n"
            "SQL:"
        ).format(
            schema=str(self.schema or "").strip(),
            question=str(question or "").strip(),
        )

    def _repair_prompt(self, question, failed_sql, error, attempt) -> str:
        return (
            "Database schema:\n"
            "{schema}\n\n"
            "Question: {question}\n\n"
            "Your previous SQL query (attempt {attempt}) FAILED to execute:\n"
            "{sql}\n\n"
            "The database returned this error:\n"
            "{error}\n\n"
            "Rewrite the query so that it executes successfully on this "
            "database. Check that every table and column name really exists "
            "in the schema, fix the specific problem the error complains "
            "about, and remember the dialect is SQLite (use || for string "
            "concatenation, strftime for dates, LIMIT to restrict row "
            "counts).\n"
            "Output only the corrected SQL query.\n"
            "SQL:"
        ).format(
            schema=str(self.schema or "").strip(),
            question=str(question or "").strip(),
            attempt=attempt,
            sql=failed_sql if failed_sql else "(no SQL was produced)",
            error=self._clip(error),
        )

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _tidy(sql: str) -> str:
        """Normalise a candidate: strip whitespace and trailing semicolons."""
        sql = (sql or "").strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    def _clip(self, text) -> str:
        text = str(text or "").strip()
        if not text:
            return "(the database returned no error message)"
        if len(text) <= self.max_error_chars:
            return text
        return text[: self.max_error_chars] + " ...[truncated]"

    def _generate(self, prompt: str) -> str:
        """One greedy LLM call, returning the extracted (possibly empty) SQL."""
        raw = self.llm(prompt, system=self.system_prompt, temperature=0.0, n=1)
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else ""
        try:
            return bridge.extract_sql(str(raw))
        except Exception:
            return ""

    def _run(self, sql: str) -> dict:
        """Execute a candidate, converting any crash into an error dict."""
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: executor blow-ups count as errors
            return {"ok": False, "rows": [], "error": "executor raised: %s" % exc}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "unexpected executor response"}
        return result

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        # ---- stage 0: initial greedy generation ------------------------
        sql = self._tidy(self._generate(self._initial_prompt(question)))
        fallback = sql  # the model's most direct answer to the question

        error = ""
        for round_no in range(self.max_repair_rounds + 1):
            # ---- execute the current candidate -------------------------
            if sql:
                result = self._run(sql)
                ok = bool(result.get("ok"))
                error = str(result.get("error") or "").strip() or (
                    "execution failed with no error message"
                )
            else:
                ok = False
                error = "the previous model output contained no SQL statement"

            if ok:
                # First candidate that actually runs wins.
                return sql

            if round_no >= self.max_repair_rounds:
                break  # repair budget exhausted

            # ---- repair round: feed the failure back to the model ------
            repaired = self._tidy(
                self._generate(
                    self._repair_prompt(
                        question, sql, error, round_no + 1
                    )
                )
            )
            if repaired:
                sql = repaired
                if not fallback:
                    fallback = repaired
            else:
                # Model went silent; the next round reports that as the error.
                sql = ""

        # Nothing ever executed cleanly: fall back to the model's original
        # direct answer rather than a speculative (still broken) rewrite.
        return fallback or sql or ""