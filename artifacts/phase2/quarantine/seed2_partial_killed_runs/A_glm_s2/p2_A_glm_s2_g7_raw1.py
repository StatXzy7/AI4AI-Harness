"""Execution-guided repair harness: a greedy first draft is executed against the database, and each failing query together with its live error message is fed back to the model for up to three corrective regeneration rounds."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G7(SQLHarness):
    """Greedy draft followed by an execution-error feedback loop.

    Control flow:
      1. One greedy draft SQL is generated from (schema, question).
      2. The draft is executed against the real database.
      3. If execution fails, the failing SQL plus the exact database error
         are fed back into a repair prompt and a corrected query is regenerated.
      4. Steps 2-3 repeat for at most three repair rounds; the first query
         that executes successfully is returned.
    """

    MAX_ATTEMPTS = 4  # one initial generation plus at most three repair rounds
    MAX_ERROR_CHARS = 600

    SYSTEM_DRAFT = (
        "You are an expert text-to-SQL engine targeting SQLite. "
        "Given a database schema and a natural-language question, write exactly one "
        "SQL query that answers the question. Use only tables and columns that appear "
        "in the schema, and prefer simple, executable queries. "
        "Output the SQL statement only: no explanation, no markdown, no commentary."
    )

    SYSTEM_REPAIR = (
        "You are an expert text-to-SQL repair engine targeting SQLite. "
        "A generated SQL query failed when it was executed against the database. "
        "You are given the schema, the question, the failing query, and the exact "
        "database error message. Diagnose the failure and output one corrected SQL "
        "query. Typical fixes: use exact table and column names from the schema, fix "
        "join or GROUP BY clauses, quote string literals correctly, and remove any "
        "non-SQLite syntax. Output the corrected SQL statement only: no explanation, "
        "no markdown, no commentary."
    )

    def solve(self, question: str) -> str:
        sql = self._draft(question)
        feedback = None

        for _ in range(self.MAX_ATTEMPTS):
            # After a failure, regenerate using the failing SQL + error message.
            if feedback is not None:
                sql = self._repair(question, sql, feedback)

            if not sql.strip():
                feedback = (
                    "Execution failed: the previous model output contained no SQL "
                    "statement. Respond with a single valid SQL SELECT query."
                )
                continue

            result = self._execute(sql)
            if result.get("ok"):
                return sql

            feedback = self._report_failure(result)

        # No attempt succeeded; return the last (repaired) query so the
        # evaluator can still score it. Degenerate fallback keeps output valid.
        return sql if sql.strip() else "SELECT 1"

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _draft(self, question: str) -> str:
        prompt = (
            "Database schema:\n"
            "%s\n\n"
            "Question: %s\n\n"
            "Write one SQL query that answers the question. "
            "Return only the SQL query."
            % (self._schema_text(), question)
        )
        text = self._call(prompt, self.SYSTEM_DRAFT)
        return self._clean(self._extract(text))

    def _repair(self, question: str, broken_sql: str, feedback: str) -> str:
        prompt = (
            "Database schema:\n"
            "%s\n\n"
            "Question: %s\n\n"
            "Failing SQL query:\n"
            "%s\n\n"
            "Execution feedback:\n"
            "%s\n\n"
            "Output one corrected SQL query that answers the question and executes "
            "successfully against the schema. Return only the corrected SQL query."
            % (
                self._schema_text(),
                question,
                broken_sql if broken_sql.strip() else "(empty)",
                feedback,
            )
        )
        text = self._call(prompt, self.SYSTEM_REPAIR)
        candidate = self._clean(self._extract(text))
        # Never regress: if a repair round produced nothing usable, keep the
        # previous query so the loop retries with fresh feedback.
        return candidate if candidate.strip() else broken_sql

    def _call(self, prompt: str, system: str) -> str:
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else ""

    def _extract(self, text: str) -> str:
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            return ""
        return sql if isinstance(sql, str) else ""

    def _execute(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
        except Exception as exc:  # defensive: treat harness blowups as failures
            return {"ok": False, "rows": [], "error": "exception during execution: %s" % exc}
        return result if isinstance(result, dict) else {}

    def _report_failure(self, result: dict) -> str:
        err = str(result.get("error") or "").strip()
        if not err:
            err = "the query failed to execute (the database returned no error text)"
        if len(err) > self.MAX_ERROR_CHARS:
            err = err[: self.MAX_ERROR_CHARS] + " ...[truncated]"
        return "sqlite error: %s" % err

    def _schema_text(self) -> str:
        return (self.schema or "").strip() or "(no schema provided)"

    @staticmethod
    def _clean(sql: str) -> str:
        if not sql:
            return ""
        s = sql.strip()
        while s.endswith(";"):
            s = s[:-1].rstrip()
        return s