"""Execution-guided repair loop: the harness generates SQL greedily, executes every candidate, and feeds validation and database errors back into the frozen solver for up to three corrective regenerations."""
# MECHANISM: repair

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G1(SQLHarness):
    """Weak-solver wrapper that repairs failing SQL using execution feedback.

    Control flow (a real change over a single greedy call):

        generate -> [validate + execute] --ok--> return
                        |
                     error string
                        v
                  regenerate (the prompt now carries the failing SQL and the
                  engine's error message) -> [validate + execute] -> ...
                  repeated for at most ``MAX_REPAIRS`` rounds.

    The first candidate that executes cleanly is returned; otherwise the
    last regenerated candidate is returned as the best effort.
    """

    MAX_REPAIRS = 3
    MAX_ERROR_CHARS = 600

    # Read-only gate: anything that mutates the database (or is not a query)
    # is rejected before it ever reaches the engine, and the rejection reason
    # is fed back exactly like an engine error.
    _WRITE_STMT = re.compile(
        r"^\s*(drop|delete|insert|update|alter|truncate|create|replace|"
        r"attach|detach|pragma|vacuum|reindex)\b",
        re.IGNORECASE,
    )
    # A semicolon followed by another SQL keyword means multiple statements.
    _MULTI_STMT = re.compile(
        r";\s*(select|with|values|insert|update|delete|drop|create|alter|"
        r"truncate|replace|attach|detach|pragma|explain|begin|commit|"
        r"rollback|analyze|vacuum|reindex)\b",
        re.IGNORECASE,
    )

    SYSTEM = (
        "You are an expert SQLite analyst. You translate natural-language questions "
        "into exactly one read-only SQLite SELECT statement, using only the tables and "
        "columns that appear in the supplied schema. You answer with SQL only."
    )

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        # Stage 1: one greedy generation from (schema, question).
        sql = self._generate(self._initial_prompt(question))
        error = self._validate_and_execute(sql)

        # Stage 2: repair loop -- execution errors drive regeneration.
        repairs = 0
        while error is not None and repairs < self.MAX_REPAIRS:
            candidate = self._generate(
                self._repair_prompt(question, sql, error, repairs)
            )
            if self._same(candidate, sql):
                # The frozen solver repeated, verbatim, the query that just
                # failed; another identical round cannot help.
                break
            sql = candidate
            error = self._validate_and_execute(sql)
            repairs += 1

        if not sql or not sql.strip():
            sql = "SELECT 1"  # never hand back an empty string
        return sql

    # ----------------------------------------------------------- prompting

    def _initial_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            + (self.schema or "")
            + "\n\nQuestion: "
            + question
            + "\n\n"
            "Task: write ONE SQLite SELECT statement that answers the question.\n"
            "Rules:\n"
            "- Read-only: exactly one SELECT statement (a leading WITH clause is fine).\n"
            "- Use only table names and column names that appear in the schema.\n"
            "- Do not invent tables, columns, or values.\n"
            "- Output only the SQL statement: no prose, no markdown, no code fences."
        )

    def _repair_prompt(self, question: str, failed_sql: str, error: str, attempt: int) -> str:
        shown = (
            failed_sql.strip()
            if failed_sql and failed_sql.strip()
            else "(no SQL statement was produced)"
        )
        return (
            "Database schema:\n"
            + (self.schema or "")
            + "\n\nQuestion: "
            + question
            + "\n\n"
            "Failed attempt #"
            + str(attempt + 1)
            + ":\n"
            + shown
            + "\n\nWhy it failed:\n"
            + error
            + "\n\n"
            "Task: rewrite the query so that it executes without errors against the "
            "schema above and still answers the question. Fix table names, column "
            "names, quoting, joins, aggregation, or syntax wherever they are wrong. "
            "Output only the corrected SQL statement: no prose, no markdown, no code fences."
        )

    def _generate(self, prompt: str) -> str:
        try:
            text = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        except Exception:
            text = ""
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        try:
            sql = bridge.extract_sql(str(text or ""))
        except Exception:
            sql = str(text or "")
        return self._tidy(sql)

    # ------------------------------------------------------ check + repair

    def _validate_and_execute(self, sql: str):
        """Return ``None`` when *sql* runs cleanly, else an error message to repair."""
        if not sql or not sql.strip():
            return "no SQL statement was produced"
        if self._WRITE_STMT.match(sql):
            return (
                "the statement is not a read-only query; only a single SELECT "
                "(optionally preceded by a WITH clause) is allowed"
            )
        if self._MULTI_STMT.search(sql):
            return "more than one SQL statement was produced; exactly one is allowed"
        try:
            result = self.execute(sql)
        except Exception as exc:  # a crashing bridge must not kill the harness
            return ("executing the query raised: %s" % exc)[: self.MAX_ERROR_CHARS]
        if isinstance(result, dict):
            if result.get("ok"):
                return None
            err = result.get("error") or "the query failed to execute"
            return str(err)[: self.MAX_ERROR_CHARS]
        return "the query failed to execute"

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _tidy(sql: str) -> str:
        if not sql:
            return ""
        s = sql.strip()
        while s.endswith(";"):
            s = s[:-1].rstrip()
        return s

    @staticmethod
    def _norm(sql: str) -> str:
        return " ".join((sql or "").split()).lower()

    @classmethod
    def _same(cls, a: str, b: str) -> bool:
        return cls._norm(a) == cls._norm(b)