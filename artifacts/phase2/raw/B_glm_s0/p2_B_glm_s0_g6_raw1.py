"""Greedy text-to-SQL generation hardened by an execution-repair loop: each candidate SQL is run against the database, and any resulting error message is fed back into the prompt to drive up to three corrective regenerations."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G6(SQLHarness):
    """One greedy guess, then up to MAX_REPAIRS error-driven rewrites.

    Control flow (a real change vs. a single greedy call):

      1. Ask the LLM for a SELECT statement (greedy, temperature 0).
      2. Execute that statement against the live database.
      3. If it executes cleanly, return it immediately.
      4. Otherwise, capture the database's error message, show the model its
         failed SQL together with that error and the schema, and ask for a
         corrected statement.
      5. Repeat until the SQL executes, the repair budget is exhausted, or
         the model starts repeating itself; then return the latest attempt.

    The regeneration prompts literally contain the error text returned by
    ``self.execute``, which is what makes this a repair mechanism.
    """

    MAX_REPAIRS = 3

    # Never hand these to the executor, even if the model emits them.
    FORBIDDEN_HEADS = frozenset(
        {
            "insert", "update", "delete", "drop", "alter", "create",
            "replace", "attach", "detach", "vacuum", "reindex", "pragma",
        }
    )

    SYSTEM = (
        "You are an expert text-to-SQL engine for SQLite. "
        "You output exactly one SQL SELECT statement and nothing else."
    )

    # ------------------------------------------------------------------ #
    # Main entry point                                                     #
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        sql = self._initial_sql(question)
        if not sql:
            # Generator produced nothing usable; emit a safe placeholder.
            return "SELECT 1"

        seen = {self._key(sql)}
        for attempt in range(1 + self.MAX_REPAIRS):
            result = self._run(sql)
            if result.get("ok"):
                return sql  # verified executable on the real database

            if attempt == self.MAX_REPAIRS:
                break  # repair budget exhausted

            error = self._error_of(result)
            fixed = self._repair_sql(question, sql, error)
            if not fixed:
                break  # regeneration gave us nothing new to try
            key = self._key(fixed)
            if key in seen:
                break  # model is looping on the same wrong statement
            seen.add(key)
            sql = fixed

        return sql  # best effort: latest attempt, even if unverified

    # ------------------------------------------------------------------ #
    # Prompting stages                                                     #
    # ------------------------------------------------------------------ #

    def _initial_sql(self, question: str) -> str:
        prompt = (
            "You are given the schema of a SQLite database and a question.\n"
            "Write a single SQLite SELECT statement that answers the question.\n"
            "\n"
            "Rules:\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Do not invent tables, columns, or values.\n"
            "- Output only the SQL statement: no explanation, no markdown.\n"
            "\n"
            "Database schema:\n{schema}\n"
            "\n"
            "Question: {question}\n"
            "\n"
            "SQL:"
        ).format(schema=self._schema_text(), question=question)
        return self._extract(self._call(prompt))

    def _repair_sql(self, question: str, broken_sql: str, error: str) -> str:
        prompt = (
            "You are given the schema of a SQLite database, a question, and a "
            "previous SQL attempt that FAILED to execute.\n"
            "\n"
            "Database schema:\n{schema}\n"
            "\n"
            "Question: {question}\n"
            "\n"
            "Failed SQL:\n{sql}\n"
            "\n"
            "Error message returned by the database:\n{error}\n"
            "\n"
            "Rewrite the SQL so that it executes successfully against this "
            "schema and still answers the question. Re-check every table and "
            "column name against the schema and fix the cause of the error.\n"
            "Output only the corrected SQL statement: no explanation, no "
            "markdown.\n"
            "\n"
            "SQL:"
        ).format(
            schema=self._schema_text(),
            question=question,
            sql=broken_sql,
            error=error,
        )
        return self._extract(self._call(prompt))

    def _call(self, prompt: str) -> str:
        out = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if out is None:
            return ""
        return out if isinstance(out, str) else str(out)

    # ------------------------------------------------------------------ #
    # Execution helpers                                                    #
    # ------------------------------------------------------------------ #

    def _run(self, sql: str) -> dict:
        stripped = sql.strip()
        if stripped:
            first = stripped.split(None, 1)[0].lower()
            if first in self.FORBIDDEN_HEADS:
                return {
                    "ok": False,
                    "rows": [],
                    "error": (
                        "refused to execute: statements starting with %r are "
                        "not allowed; rewrite the answer as a read-only "
                        "SELECT query" % first
                    ),
                }
        try:
            result = self.execute(sql)
        except Exception as exc:  # executor raised instead of reporting
            return {"ok": False, "rows": [], "error": "executor raised: %s" % (exc,)}
        if isinstance(result, dict):
            return result
        return {
            "ok": False,
            "rows": [],
            "error": "executor returned an unexpected result: %r" % (result,),
        }

    def _error_of(self, result: dict) -> str:
        err = result.get("error")
        if isinstance(err, str) and err.strip():
            return err.strip()[:600]
        return "execution failed (no error message was provided)"

    # ------------------------------------------------------------------ #
    # Small utilities                                                      #
    # ------------------------------------------------------------------ #

    def _schema_text(self) -> str:
        schema = self.schema if isinstance(self.schema, str) else ""
        schema = schema.strip()
        return schema if schema else "(no schema provided)"

    def _extract(self, text: str) -> str:
        sql = ""
        text = (text or "").strip()
        if text:
            try:
                sql = bridge.extract_sql(text)
            except Exception:
                sql = ""
            if not sql:
                sql = text  # last resort: treat the whole output as SQL
        if not isinstance(sql, str):
            sql = str(sql)
        sql = sql.strip()
        while sql.endswith(";"):
            sql = sql[:-1].strip()
        return sql

    @staticmethod
    def _key(sql: str) -> str:
        """Normalization used only for duplicate-attempt detection."""
        return " ".join(sql.split()).lower()