"""Greedy SQL generation wrapped in an execution-feedback repair loop: every candidate query is executed, and any database error is fed back to the solver for corrective regeneration (up to 3 total attempts)."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G1(SQLHarness):
    """Text-to-SQL harness that repairs candidate SQL using real execution errors.

    Control flow:
      1. Greedily generate a candidate SQL for the question against the schema.
      2. Execute the candidate against the live database.
      3. If execution succeeds (ok=True, regardless of row count -- an empty
         result can be a correct answer), return it immediately.
      4. If execution fails, append the offending SQL plus the actual database
         error message to the prompt and ask the solver for a corrected query.
         Repeat for up to MAX_ATTEMPTS total generations.
      5. If the repair round regenerates the exact same failing SQL, stop early
         (a deterministic retry would fail identically).
      6. If every attempt fails, return the last extracted SQL as the best guess.
    """

    MAX_ATTEMPTS = 3
    MAX_ERROR_CHARS = 500

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _generate(self, prompt, system, temperature=0.0):
        """Call the frozen LLM once and coerce whatever it returns into text."""
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if len(out) else ""
        if isinstance(out, dict):
            out = out.get("text") or out.get("content") or out.get("response") or ""
        if out is None:
            out = ""
        return str(out)

    def _execute(self, sql):
        """Run SQL defensively. Always returns (ok, error_message)."""
        try:
            res = self.execute(sql)
        except Exception as exc:  # executor raised instead of returning a dict
            return False, "executor raised: %s" % (exc,)
        if not isinstance(res, dict):
            return False, "executor returned a non-dict result: %r" % (res,)
        ok = bool(res.get("ok"))
        err = str(res.get("error") or "").strip()
        if not ok and not err:
            err = "query failed (ok=False) with no error message"
        return ok, err[: self.MAX_ERROR_CHARS]

    @staticmethod
    def _tidy(sql):
        """Normalize an extracted SQL string: trim whitespace and trailing ';'."""
        sql = (sql or "").strip()
        while sql.endswith(";"):
            sql = sql[:-1].rstrip()
        return sql

    # ------------------------------------------------------------------ #
    # Main control flow
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        if not isinstance(schema, str):
            schema = str(schema)

        system = (
            "You are an expert text-to-SQL engine. Given a database schema and a "
            "natural-language question, output exactly one SQLite SELECT query. "
            "Output only the SQL itself: no prose, no explanation, no markdown."
        )
        base_prompt = (
            "Database schema:\n%s\n\nQuestion: %s\n\n"
            "Respond with a single SQL query that answers the question."
            % (schema, question)
        )

        best_sql = ""    # last successfully extracted SQL (returned if all fails)
        last_sql = ""    # SQL (or raw snippet) produced by the previous attempt
        last_error = ""  # error message produced by the previous attempt

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            if attempt == 1:
                prompt = base_prompt
                temperature = 0.0
            else:
                prompt = (
                    "%s\n\n"
                    "--- repair round %d ---\n"
                    "Your previous SQL was:\n%s\n\n"
                    "Executing it against the database raised this error:\n%s\n\n"
                    "Write a corrected SQL query that fixes this error. "
                    "Respond with only the corrected query."
                    % (base_prompt, attempt, last_sql, last_error)
                )
                # Stay greedy on the first repair; nudge temperature on the last
                # attempt so the model can escape a deterministic failure loop.
                temperature = 0.0 if attempt == 2 else 0.4

            text = self._generate(prompt, system, temperature)
            sql = self._tidy(bridge.extract_sql(text))

            if not sql:
                # Nothing extractable: treat that itself as the error to repair.
                last_sql = text.strip()[:300]
                last_error = "no SQL statement could be extracted from the previous answer"
                continue

            if sql == last_sql:
                # Identical regeneration would fail identically; stop early.
                break

            best_sql = sql
            last_sql = sql
            ok, error = self._execute(sql)
            if ok:
                # A successful execution (even with zero rows) is accepted.
                return sql
            last_error = error

        # All attempts failed (or produced nothing usable); return best guess.
        return best_sql or last_sql