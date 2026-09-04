"""Generate SQL, execute it, classify any failure as syntax/schema/semantics in the control flow, and apply a class-specific repair strategy for up to 2 rounds."""

import difflib
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS0ErrorClassify(SQLHarness):
    """Error-classifying Text-to-SQL harness.

    Control flow:
      1. Generate an initial SQL candidate from (schema, question).
      2. Execute the candidate against the database.
      3. On failure, classify the error into exactly one bucket:
           - "syntax"    : the SQL cannot be parsed/compiled by the engine.
           - "schema"    : the SQL references identifiers absent from the schema.
           - "semantics" : the SQL runs but is logically wrong (e.g. 0 rows) or
                           misuses SQL constructs (aggregates, types).
      4. Apply the repair strategy attached to that bucket (_repair_syntax /
         _repair_schema / _repair_semantics), each with its own prompt,
         temperature, and deterministic hints.
      5. Repeat steps 2-4 for at most MAX_REPAIR_ROUNDS repairs, then return
         the best candidate seen (preferring the last query that executed).
    """

    MAX_REPAIR_ROUNDS = 2

    # Substring signatures used to bucket the executor's error text.
    _SYNTAX_PATTERNS = (
        "syntax error",
        "unrecognized token",
        "unexpected token",
        "unterminated string",
        "incomplete input",
        "parse error",
        "could not prepare",
    )
    _SCHEMA_PATTERNS = (
        "no such table",
        "no such column",
        "no such function",
        "ambiguous column",
        "unknown column",
        "unknown table",
        "has no column named",
        "no column named",
    )
    # Extractors for the offending identifier in schema-class errors.
    _MISSING_IDENT_RES = (
        re.compile(r"no such (?:table|column|function)\s*:\s*([^\s;]+)", re.IGNORECASE),
        re.compile(r"has no column named\s+([^\s;]+)", re.IGNORECASE),
        re.compile(r"ambiguous column name\s*:\s*([^\s;]+)", re.IGNORECASE),
    )

    # ------------------------------------------------------------------ main
    def solve(self, question: str) -> str:
        sql = self._generate_initial(question)
        best_ok_sql = None  # last candidate that at least executed successfully

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            result = self._safe_execute(sql)
            ok = bool(result.get("ok"))
            rows = result.get("rows") or []

            if ok and rows:
                return sql  # success with a non-empty answer -> done

            # ---- classify the failure (control flow, not just prompt) -------
            if ok:
                best_ok_sql = sql  # executable but empty: keep as fallback
                failure_class = "semantics"
                error_text = (
                    "Query executed successfully but returned 0 rows; the logic "
                    "is probably wrong (filters, joins, values, or aggregation)."
                )
            else:
                error_text = str(result.get("error") or "unknown execution error")
                failure_class = self._classify_error(error_text)

            if round_idx >= self.MAX_REPAIR_ROUNDS:
                break  # repair budget exhausted -> best effort below

            # ---- class-specific repair --------------------------------------
            repaired = self._repair(
                question=question,
                sql=sql,
                failure_class=failure_class,
                error_text=error_text,
                round_idx=round_idx,
            )
            if repaired:
                sql = repaired

        # Best effort: prefer the last executable (but empty) candidate over a
        # final candidate that does not run at all.
        return best_ok_sql or sql

    # ------------------------------------------------------------- execution
    def _safe_execute(self, sql: str) -> dict:
        """Execute defensively: executor exceptions become classifiable errors."""
        try:
            result = self.execute(sql)
            if isinstance(result, dict):
                return result
            return {
                "ok": False,
                "rows": [],
                "error": "unexpected executor response: %r" % (result,),
            }
        except Exception as exc:
            return {"ok": False, "rows": [], "error": "%s: %s" % (type(exc).__name__, exc)}

    # ---------------------------------------------------------- classification
    def _classify_error(self, error_text: str) -> str:
        """Map raw executor error text to 'syntax' | 'schema' | 'semantics'."""
        msg = error_text.lower()
        # Schema first: it is the most specific and actionable bucket.
        if any(pat in msg for pat in self._SCHEMA_PATTERNS):
            return "schema"
        if any(pat in msg for pat in self._SYNTAX_PATTERNS):
            return "syntax"
        # Everything else (misuse of aggregate, datatype mismatch, constraint,
        # empty results, ...) is treated as a logical/semantic failure.
        return "semantics"

    def _missing_identifier(self, error_text: str) -> str:
        for rx in self._MISSING_IDENT_RES:
            m = rx.search(error_text)
            if m:
                return m.group(1)
        return ""

    def _schema_identifiers(self) -> list:
        return sorted(set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", self.schema or "")))

    # ---------------------------------------------------------------- repairs
    def _repair(self, question: str, sql: str, failure_class: str,
                error_text: str, round_idx: int) -> str:
        """Dispatch to the strategy bound to the failure class."""
        if failure_class == "syntax":
            return self._repair_syntax(question, sql, error_text)
        if failure_class == "schema":
            return self._repair_schema(question, sql, error_text)
        return self._repair_semantics(question, sql, error_text, round_idx)

    def _repair_syntax(self, question: str, sql: str, error_text: str) -> str:
        """SYNTAX strategy: minimal edit — fix compilation only, preserve logic."""
        system = (
            "You are an expert SQLite syntax fixer. Fix ONLY the syntax so the "
            "query compiles under SQLite. Do NOT change the tables, columns, "
            "joins, filters, or aggregation logic."
        )
        prompt = (
            "Database schema:\n{schema}\n\n"
            "Question: {question}\n\n"
            "This SQL failed to parse:\n