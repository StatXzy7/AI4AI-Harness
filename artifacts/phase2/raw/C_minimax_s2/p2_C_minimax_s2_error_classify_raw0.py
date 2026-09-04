"""Wraps a frozen weak Text-to-SQL solver with error-classifying repair loop (syntax/schema/semantics), up to 2 rounds."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2ErrorClassify(SQLHarness):
    # ------------------------------------------------------------------
    # Prompt templates
    # ------------------------------------------------------------------
    BASE_SYSTEM = (
        "You are a careful Text-to-SQL generator. Given a database schema "
        "and a natural language question, produce ONE single SQLite-compatible "
        "SQL query. Return ONLY the SQL (no prose, no markdown fences)."
    )

    BASE_USER_TEMPLATE = (
        "Schema:\n{schema}\n\n"
        "Question: {question}\n\n"
        "SQL:"
    )

    REPAIR_USER_TEMPLATE = (
        "Schema:\n{schema}\n\n"
        "Question: {question}\n\n"
        "Previous SQL attempt: {prev_sql}\n\n"
        "Execution result:\n"
        "ok={ok}\n"
        "error={error}\n"
        "rows_preview={rows}\n\n"
        "Diagnostic classification: {diagnosis}\n\n"
        "Fix instruction: {fix_instruction}\n\n"
        "Return ONLY the corrected SQL."
    )

    # Heuristic SQL-keyword list used to tell a SQL-ish blob from free prose.
    _SQL_KEYWORDS = re.compile(
        r"\b(SELECT|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|LIMIT|JOIN|"
        r"LEFT|RIGHT|INNER|OUTER|ON|AS|AND|OR|NOT|NULL|IS|IN|"
        r"INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TABLE|INDEX|"
        r"COUNT|SUM|AVG|MAX|MIN|DISTINCT|UNION|HAVING|EXISTS|"
        r"BETWEEN|LIKE|CASE|WHEN|THEN|ELSE|END|CAST|COUNT)\b",
        re.IGNORECASE,
    )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        llm = getattr(self, "llm", None)
        if llm is None:
            raise RuntimeError("P2P2CMinimaxS2ErrorClassify requires self.llm")

        current_sql: str = ""

        for round_idx in range(3):  # 1 initial + up to 2 repair rounds
            if round_idx == 0:
                prompt = self.BASE_USER_TEMPLATE.format(
                    schema=schema, question=question
                )
                system = self.BASE_SYSTEM
            else:
                diagnosis, fix = self._diagnose(current_sql)
                prompt = self.REPAIR_USER_TEMPLATE.format(
                    schema=schema,
                    question=question,
                    prev_sql=current_sql,
                    ok=self._last_exec_ok,
                    error=self._last_exec_error,
                    rows=self._last_rows_preview,
                    diagnosis=diagnosis,
                    fix_instruction=fix,
                )
                system = self.BASE_SYSTEM

            raw = llm(prompt, system=system, temperature=0.0, n=1)

            # Prefer the harness-provided extractor; fall back to a local one.
            try:
                candidate = bridge.extract_sql(raw)  # type: ignore[attr-defined]
            except Exception:
                candidate = ""
            if not candidate:
                candidate = self._local_extract_sql(raw)

            candidate = (candidate or "").strip()
            if not candidate:
                # Nothing usable came back -- keep current best and continue.
                continue

            current_sql = candidate
            exec_result = self.execute(current_sql)
            self._remember_exec(exec_result)

            if exec_result.get("ok"):
                return current_sql

            # On the last round, stop repairing and return the last attempt.
            if round_idx >= 2:
                break

        return current_sql

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _remember_exec(self, result: Dict[str, Any]) -> None:
        self._last_exec_ok = bool(result.get("ok"))
        self._last_exec_error = str(result.get("error", "") or "")
        rows = result.get("rows", []) or []
        try:
            self._last_rows_preview = repr(rows[:3])
        except Exception:
            self._last_rows_preview = "<unprintable>"

    # --- Classification ------------------------------------------------
    def _diagnose(self, sql: str) -> Tuple[str, str]:
        """
        Classify the last execution failure into one of:
        SYNTAX, SCHEMA, SEMANTICS, or UNKNOWN.
        Returns (diagnosis, fix_instruction).
        """
        err = (self._last_exec_error or "").lower()
        sql_lc = (sql or "").lower()

        # 1) SYNTAX errors: parser/lex complaints
        syntax_markers = (
            "syntax error",
            "near \"",
            "unrecognized token",
            "unexpected",
            "incomplete input",
            "unterminated",
            "no such column" in err and "ambiguous" in err,  # not really syntax
        )
        if any(m in err for m in syntax_markers):
            return "SYNTAX", self._fix_syntax()

        # 2) SCHEMA errors: missing/unknown table or column, or type mismatch
        schema_markers = (
            "no such table",
            "no such column",
            "ambiguous column",
            "table not found",
            "column not found",
            "unknown table",
            "unknown column",
            "has no column",
            "does not have a column",
        )
        if any(m in err for m in schema_markers):
            return "SCHEMA", self._fix_schema()

        # 3) SEMANTICS: query runs but returns empty / wrong shape
        if self._last_exec_ok is False and self._last_rows_preview in ("[]", "()", "()", "()"):
            return "SEMANTICS_EMPTY", self._fix_semantics_empty()
        if self._last_exec_ok is False:
            # Non-OK with rows present: treat as semantic/logic error.
            return "SEMANTICS", self._fix_semantics()

        return "UNKNOWN", "Re-derive the SQL from the question and schema."

    # --- Strategy-specific fix instructions --------------------------
    def _fix_syntax(self) -> str:
        return (
            "The previous SQL has a SYNTAX error. Re-emit it as a single, "
            "well-formed SQLite statement. Make sure every parenthesis is "
            "balanced, every string literal is properly quoted with single "
            "quotes, and every keyword is spelled correctly. Do not wrap the "
            "answer in markdown fences or add commentary."
        )

    def _fix_schema(self) -> str:
        return (
            "The previous SQL references a TABLE or COLUMN that does not exist "
            "in the schema. Cross-check EVERY table and column name against the "
            "Schema section above. Use only names that literally appear in the "
            "Schema. Qualify ambiguous columns with their table name (e.g., "
            "orders.id instead of just id). Re-emit the corrected SQL."
        )

    def _fix_semantics(self) -> str:
        return (
            "The previous SQL executed but produced rows that do not answer the "
            "question. Re-read the question carefully: check JOIN conditions, "
            "WHERE filters, GROUP BY columns, aggregation level, and ORDER BY. "
            "Make sure the selected columns and the filtering logic match what "
            "is being asked. Re-emit the corrected SQL."
        )

    def _fix_semantics_empty(self) -> str:
        return (
            "The previous SQL executed successfully but returned 0 rows. "
            "Loosen or correct the filters: verify JOIN keys, comparison "
            "operators (= vs LIKE), case sensitivity, and that you are not "
            "filtering on a column from the wrong table. Re-emit the corrected "
            "SQL."
        )

    # --- Local SQL extraction (fallback) -------------------------------
    def _local_extract_sql(self, text: str) -> str:
        if not text:
            return ""
        # Strip code fences if present.
        fenced = re.search(r"