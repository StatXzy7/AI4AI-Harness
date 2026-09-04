"""Generate an initial SQL candidate, execute it, classify any failure as syntax, schema, or semantics, and apply a class-specific repair for up to two rounds, returning the best executable query observed."""

import re

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS0ErrorClassify"]


class P2P2CGlmS0ErrorClassify(SQLHarness):
    """Weak-solver wrapper that repairs SQL by failure class.

    Control flow (mirrored in :meth:`solve`, not just the prompts):

    1. GENERATE an initial SQL candidate from ``(question, schema)``.
    2. EXECUTE the candidate against the database.
    3. CLASSIFY the failure deterministically into exactly one bucket:
         * ``"syntax"``    -- the statement does not parse;
         * ``"schema"``    -- tables/columns referenced are not in the schema;
         * ``"semantics"`` -- runtime/logic failures, plus queries that
                              execute but return zero rows.
    4. REPAIR with a bucket-specific strategy:
         * syntax    -> minimal rewrite, logic frozen, error text only;
         * schema    -> re-bind identifiers to the authorized schema;
         * semantics -> re-derive the query from the question, enriched with
                        sample rows probed from the tables it touched.
    5. Repeat steps 2-4 for at most ``MAX_ROUNDS`` repair rounds, then return
       the best candidate seen (executable > non-executable, non-empty >
       empty; ties go to the most recent attempt).
    """

    MAX_ROUNDS = 2      # repair rounds after the initial generation
    PROBE_TABLES = 3    # tables sampled for semantic repairs
    PROBE_ROWS = 3      # rows sampled per probed table
    SAMPLE_CLIP = 600   # max characters of rendered sample data per table

    # Error-text markers for the SCHEMA bucket (checked first: most specific).
    _SCHEMA_MARKERS = (
        "no such table", "no such column", "has no column", "no column named",
        "unknown column", "unknown table", "unknown field", "undefined column",
        "undefined table", "column not found", "table not found",
        "ambiguous column", "ambiguous reference", "does not exist",
        "not found in", "invalid column", "invalid table", "invalid identifier",
        "missing table", "missing column",
    )

    # Error-text markers for the SYNTAX bucket.
    _SYNTAX_MARKERS = (
        "syntax", "parse error", "error parsing", "parsing failed",
        "unrecognized token", "unexpected token", "incomplete input",
        "unterminated", "extraneous input", "missing keyword", "invalid token",
        "expected", "unexpected", "right syntax to use", "check the manual",
        "near", "malformed", "bad sql", "invalid sql",
    )

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        question = (question or "").strip()
        self.repair_trace = []

        # -- step 1: initial generation -----------------------------------
        sql = self._generate(question)
        result = (
            self._safe_execute(sql)
            if sql
            else {"ok": False, "rows": [], "error": "no SQL statement was produced"}
        )
        best_sql = sql
        best_rank = self._rank(result)

        # -- steps 2-4: classify + class-specific repair, at most 2 rounds
        for round_index in range(self.MAX_ROUNDS):
            if self._succeeded(result):
                break  # executable AND non-empty: nothing left to repair

            bucket = self._classify(result)
            self.repair_trace.append({
                "round": round_index + 1,
                "bucket": bucket,
                "ok": result["ok"],
                "rows": len(result["rows"]),
                "error": result["error"],
            })

            repaired = self._repair(question, sql, result, bucket)
            if not repaired or repaired.strip() == (sql or "").strip():
                break  # repair changed nothing: avoid an identical retry loop

            sql = repaired
            result = self._safe_execute(sql)

            rank = self._rank(result)
            if rank >= best_rank:  # ties keep the most recent attempt
                best_sql, best_rank = sql, rank

        return best_sql

    # ------------------------------------------------------------------ #
    # failure classification (syntax / schema / semantics)
    # ------------------------------------------------------------------ #
    def _classify(self, result):
        """Map a failed execution result to 'syntax' | 'schema' | 'semantics'."""
        if result.get("ok"):
            # Executed cleanly but answered nothing: suspected wrong logic.
            return "semantics"
        return self._classify_error_text(result.get("error"))

    def _classify_error_text(self, error):
        err = (error or "").lower()
        if not err:
            return "semantics"
        # Unknown functions are a "rewrite the logic" problem, not a naming one.
        if "no such function" in err or ("function" in err and "does not exist" in err):
            return "semantics"
        if any(marker in err for marker in self._SCHEMA_MARKERS):
            return "schema"
        if any(marker in err for marker in self._SYNTAX_MARKERS):
            return "syntax"
        # Runtime failures (type mismatches, aggregate misuse, ...) default to
        # the semantic bucket: the query parses and binds, but it is wrong.
        return "semantics"

    # ------------------------------------------------------------------ #
    # class-specific repair strategies
    # ------------------------------------------------------------------ #
    def _repair(self, question, sql, result, bucket):
        if bucket == "syntax":
            return self._repair_syntax(sql, result)
        if bucket == "schema":
            return self._repair_schema(sql, result)
        return self._repair_semantics(question, sql, result)

    def _repair_syntax(self, sql, result):
        """SYNTAX fix: minimal rewrite, logic and identifiers frozen."""
        prompt = (
            "The SQL statement below does not parse.\n\n"
            "Broken SQL:\n%s\n\n"
            "Database error:\n%s\n\n"
            "Repair ONLY the syntax: keep the same tables, columns, operators "
            "and overall logic, changing as little as possible.\n"
            "Return the corrected SQL statement and nothing else."
            % (sql or "(none)", result.get("error") or "syntax error")
        )
        return self._sql_from_llm(prompt, system="You are a SQL syntax-repair engine.")

    def _repair_schema(self, sql, result):
        """SCHEMA fix: re-bind every identifier to the authorized schema."""
        prompt = (
            "The SQL statement below refers to tables or columns that do not "
            "exist.\n\n"
            "Authorized schema (the ONLY valid tables and columns):\n%s\n\n"
            "Broken SQL:\n%s\n\n"
            "Database error:\n%s\n\n"
            "Rewrite the statement so that every table and column name matches "
            "the authorized schema exactly (adjust joins, aliases and selected "
            "columns accordingly) while preserving the query's intent.\n"
            "Return the corrected SQL statement and nothing else."
            % (self.schema or "(no schema provided)", sql or "(none)",
               result.get("error") or "unknown table or column")
        )
        return self._sql_from_llm(prompt, system="You are a SQL schema-rebinding repair engine.")

    def _repair_semantics(self, question, sql, result):
        """SEMANTICS fix: re-derive the query from the question (+ samples)."""
        if result.get("ok"):
            observation = "the query executed successfully but returned 0 rows"
        else:
            observation = result.get("error") or "the query failed"
        samples = self._probe_samples(sql or "")
        sample_block = (
            "\n\nSample rows from tables used by the failed query:\n%s" % samples
            if samples else ""
        )
        prompt = (
            "A SQL query was written to answer a user question, but it is "