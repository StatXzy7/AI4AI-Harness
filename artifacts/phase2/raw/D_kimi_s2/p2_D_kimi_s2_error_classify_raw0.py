"""Generate SQL, execute it, classify any failure as syntax / schema / semantics, and apply a class-specific repair for up to 2 rounds."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2ErrorClassify(SQLHarness):
    """Error-classification repair loop for Text-to-SQL.

    Control flow per attempt:
      1. Execute the current SQL.
      2. If the database raises an error, classify the message in Python into:
         - "syntax"    -> grammar / parsing problems,
         - "schema"    -> unknown or ambiguous tables, columns, or functions,
         - "semantics" -> anything else (runtime / logic errors).
      3. An execution that succeeds but returns no meaningful rows is also
         treated as a "semantics" failure.
      4. Each class gets its own targeted repair prompt; at most 2 repair
         rounds are performed (initial attempt + 2 repairs = 3 executions max).
      5. If repairs never produce a non-empty result, fall back to the last
         SQL that at least executed without a database error.
    """

    MAX_REPAIR_ROUNDS = 2

    # Message substrings used for control-flow classification (checked lowercase).
    _SCHEMA_MARKERS = (
        "no such column",
        "no such table",
        "no such function",
        "no such",
        "unknown column",
        "unknown table",
        "unknown identifier",
        "ambiguous column",
        "invalid identifier",
        "does not exist",
        "no column named",
        "has no column",
        "not found",
    )
    _SYNTAX_MARKERS = (
        "syntax error",
        "syntax",
        'near "',
        "near '",
        "at or near",
        "parse error",
        "unexpected token",
        "unterminated",
        "incomplete input",
        "unrecognized token",
        "mismatched parentheses",
        "expected",
    )

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        sql = self._generate_initial(question)
        executable_fallback = ""  # last SQL that ran without a DB error

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            last_round = round_idx >= self.MAX_REPAIR_ROUNDS
            result = self.execute(sql)

            if result.get("ok"):
                if self._rows_meaningful(result.get("rows")):
                    return sql
                # Executed cleanly but empty/NULL-only -> SEMANTICS failure.
                executable_fallback = sql
                if last_round:
                    return sql
                sql = self._repair_semantics(
                    question,
                    sql,
                    "the query ran without errors but returned 0 rows (or only "
                    "NULL values), so its logic likely does not match the question",
                )
                continue

            error = (result.get("error") or "unknown database error").strip()
            if last_round:
                break

            # --- classify the failure, then dispatch a class-specific fix ---
            err_class = self._classify_error(error)
            if err_class == "schema":
                sql = self._repair_schema(question, sql, error)
            elif err_class == "syntax":
                sql = self._repair_syntax(question, sql, error)
            else:
                sql = self._repair_semantics(
                    question, sql, f"the database raised a runtime error: {error}"
                )

        return executable_fallback if executable_fallback else sql

    # ------------------------------------------------------------------ #
    # Failure classification (pure control flow, no LLM)
    # ------------------------------------------------------------------ #
    def _classify_error(self, error: str) -> str:
        msg = (error or "").lower()
        if any(marker in msg for marker in self._SCHEMA_MARKERS):
            return "schema"
        if any(marker in msg for marker in self._SYNTAX_MARKERS):
            return "syntax"
        return "semantics"

    @staticmethod
    def _extract_offender(error: str) -> str:
        """Pull the offending identifier out of a schema/syntax error message."""
        patterns = (
            r"no such column:\s*([^\s]+)",
            r"no such table:\s*([^\s]+)",
            r"no such function:\s*([^\s]+)",
            r"ambiguous column name:\s*([^\s]+)",
            r"unknown column ['\"]?([^'\"\s]+)",
            r"unknown table ['\"]?([^'\"\s]+)",
            r"column ['\"]?([^'\"\s]+)['\"]? does not exist",
            r"relation ['\"]?([^'\"\s]+)['\"]? does not exist",
            r'near "([^"]+)"',
        ]
        for pat in patterns:
            m = re.search(pat, error or "", re.IGNORECASE)
            if m:
                return m.group(1)
        return ""

    @staticmethod
    def _rows_meaningful(rows) -> bool:
        """True iff the result has at least one row with a non-NULL value."""
        if not rows:
            return False
        for row in rows:
            if isinstance(row, dict):
                values = row.values()
            elif isinstance(row, (list, tuple)):
                values = row
            else:
                values = (row,)
            if any(v is not None for v in values):
                return True
        return False

    # ------------------------------------------------------------------ #
    # LLM plumbing
    # ------------------------------------------------------------------ #
    def _ask(self, prompt: str, system: str) -> str:
        text = self.llm(prompt, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(text)
        if sql:
            return sql
        return text.strip() if isinstance(text, str) else ""

    # ------------------------------------------------------------------ #
    # Generation + class-specific repairs
    # ------------------------------------------------------------------ #
    def _generate_initial(self, question: str) -> str:
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write ONE SQLite query that answers the question. Use only tables "
            "and columns that appear in the schema. Output only the SQL — no "
            "explanation, no markdown."
        )
        return self._ask(
            prompt, system="You are an expert SQLite Text-to-SQL engine."
        )

    def _repair_syntax(self, question: str, sql: str, error: str) -> str:
        """SYNTAX-class fix: repair grammar only, keep identifiers and logic."""
        prompt = (
            "The following SQLite query has a SYNTAX error. Fix only the grammar "
            "(keywords, clause order, commas, parentheses, quoting of string "
            "literals). Do NOT change table names, column names, or the query "
            "logic unless the syntax fix strictly requires it.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Broken SQL:\n{sql}\n\n"
            f"Database error message: {error}\n\n"
            "Output only the corrected SQL."
        )
        return self._ask(
            prompt, system="You are an SQLite syntax corrector. Return only valid SQL."
        )

    def _repair_schema(self, question: str, sql: str, error: str) -> str:
        """SCHEMA-class fix: re-map identifiers to exact schema names."""
        offender = self._extract_offender(error)
        offender_note = (
            f"The database could not resolve this identifier: {offender}.\n"
            if offender
            else ""
        )
        prompt = (
            "The following SQLite query references tables or columns that DO NOT "
            "EXIST in the schema (or are ambiguous). Rewrite it using ONLY the "
            "exact table and column names listed in the schema: map every wrong "
            "identifier to the closest valid one, and qualify ambiguous columns "
            "as table.column. If the error concerns a function, replace it with "
            "an equivalent SQLite function or expression. "
            f"{offender_note}\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Broken SQL:\n{sql}\n\n"
            f"Database error message: {error}\n\n"
            "Output only the corrected SQL."
        )
        return self._ask(
            prompt,
            system="You are an SQLite schema-alignment corrector. Return only valid SQL.",
        )

    def _repair_semantics(self, question: str, sql: str, diagnosis: str) -> str:
        """SEMANTICS-class fix: grammar and identifiers are fine; repair logic."""
        prompt = (
            "The following SQLite query is syntactically valid and uses existing "
            "tables/columns, but it does NOT correctly answer the question: "
            f"{diagnosis}.\n\n"
            "Reconsider the query LOGIC only:\n"
            "- join conditions and join direction\n"
            "- WHERE filter values (case, whitespace, formatting; use LIKE when "
            "the exact stored form is uncertain)\n"
            "- choice of aggregation and GROUP BY keys\n"
            "- ORDER BY direction (ASC vs DESC) and LIMIT\n"
            "- whether the SELECTed columns match what the question actually asks\n"
            "Keep table and column names exactly as written in the schema.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Current SQL:\n{sql}\n\n"
            "Output only the corrected SQL."
        )
        return self._ask(
            prompt, system="You are an SQLite logic corrector. Return only valid SQL."
        )