"""Self-correcting SQL harness that classifies execution errors and applies targeted fixes across up to two repair rounds."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..harness_base import SQLHarness
from .. import bridge


# Prompt fragments used for each repair strategy.
_HINT_SYNTAX = (
    "The previous SQL was REJECTED BY THE PARSER / EXECUTION ENGINE for a SYNTAX error. "
    "Common causes: unmatched parentheses, missing commas between columns, unclosed string literals, "
    "typos in keywords (e.g. FORM vs FROM, SELET vs SELECT), invalid identifiers. "
    "Re-emit a corrected, valid SQL statement only. Do not add commentary."
)

_HINT_SCHEMA = (
    "The previous SQL FAILED because it referenced NON-EXISTENT schema objects "
    "(tables or columns that are not in the database). "
    "Re-read the schema description carefully and use ONLY tables and columns that actually exist. "
    "Re-emit a corrected SQL statement only. Do not add commentary."
)

_HINT_SEMANTICS = (
    "The previous SQL EXECUTED without error but produced a SEMANTICALLY WRONG or "
    "EMPTY/INCORRECT result for the question. "
    "Re-think the join structure, the filter conditions, the aggregations, and the SELECT clause. "
    "Make sure the query answers the exact question that was asked. "
    "Re-emit a corrected SQL statement only. Do not add commentary."
)


class P2P2CMinimaxS2ErrorClassify(SQLHarness):
    """Generate → Execute → Classify error → Targeted fix (up to 2 repair rounds)."""

    # ------------------------------------------------------------------ #
    #  Public entry                                                        #
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # Round 0: initial generation.
        sql = self._generate(question, error_hint="")
        for round_idx in range(2):  # at most 2 repair rounds (rounds 1 & 2)
            result = self.execute(sql)
            if result.get("ok"):
                return sql  # success

            err_class, err_msg = self._classify(result)
            hint = self._hint_for(err_class)
            sql = self._generate(question, error_hint=hint, previous_sql=sql,
                                 error_message=err_msg, err_class=err_class)
        # Final attempt: run once more, return the best-effort SQL even if it failed.
        return sql

    # ------------------------------------------------------------------ #
    #  Generation                                                          #
    # ------------------------------------------------------------------ #
    def _generate(self,
                  question: str,
                  error_hint: str = "",
                  previous_sql: Optional[str] = None,
                  error_message: Optional[str] = None,
                  err_class: Optional[str] = None) -> str:
        """Ask the underlying LLM for a SQL string (possibly conditioned on an error)."""
        system = (
            "You are a Text-to-SQL assistant. Given a natural language question and a database "
            "schema, output exactly one executable SQL statement. Output ONLY the SQL — no "
            "markdown fences, no explanation, no prose."
        )

        user_parts = []
        user_parts.append("SCHEMA:\n" + (self.schema or ""))
        user_parts.append(f"QUESTION: {question}")

        if previous_sql is not None and error_hint:
            user_parts.append(f"PREVIOUS SQL: {previous_sql}")
            if error_message:
                user_parts.append(f"ENGINE MESSAGE: {error_message}")
            user_parts.append("ISSUE TYPE: " + (err_class or "unknown"))
            user_parts.append(error_hint)

        prompt = "\n\n".join(user_parts)

        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        # If n>1 in the future, collapse to one string.
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        sql = bridge.extract_sql(raw or "")
        return sql.strip()

    # ------------------------------------------------------------------ #
    #  Error classification                                                #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _classify(result: Dict[str, Any]) -> tuple[str, str]:
        """Classify an execution failure into SYNTAX, SCHEMA, or SEMANTICS."""
        err = (result.get("error") or "").strip()
        rows = result.get("rows")

        # 1) Native driver / SQLAlchemy raises here on parse / runtime engine errors.
        #    We try to separate PARSE-time (syntax) from EXEC-time (schema / runtime) errors.
        if not result.get("ok"):
            low = err.lower()

            # --- SYNTAX / parse-time ---------------------------------------
            syntax_keys = (
                "syntax error", "syntaxerror", "parse error", "parsing error",
                "unexpected token", "unexpected end", "invalid input syntax",
                "malformed", "lexical error", "tokenizer", "you have an error in your sql",
                "check the manual that corresponds", "ora-", "dpyt",
                "incomplete sql statement", "near \"" ,
            )
            if any(k in low for k in syntax_keys):
                return "SYNTAX", err

            # --- SCHEMA (no such table / column / ambiguous column) -------
            schema_keys = (
                "no such table", "table not found", "does not exist", "undefined table",
                "no such column", "column not found", "undefined column",
                "unknown column", "invalid identifier", "ambiguous column",
                "table or view not found", "object does not exist",
                "relation \"", "column \"", "table \"", "does not exist",
            )
            if any(k in low for k in schema_keys):
                return "SCHEMA", err

            # --- Execution worked but result is wrong / empty -------------
            # Treat OK but with no rows OR an exec error that doesn't fit above
            # as SEMANTICS (e.g. type-cast failure, division by zero, filtered
            # too aggressively, missing JOIN, etc.).
            return "SEMANTICS", err

        # ok=True with rows -> already handled by the caller; this is a fallback.
        return "SEMANTICS", err

    # ------------------------------------------------------------------ #
    #  Hint selection                                                      #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _hint_for(err_class: str) -> str:
        if err_class == "SYNTAX":
            return _HINT_SYNTAX
        if err_class == "SCHEMA":
            return _HINT_SCHEMA
        return _HINT_SEMANTICS