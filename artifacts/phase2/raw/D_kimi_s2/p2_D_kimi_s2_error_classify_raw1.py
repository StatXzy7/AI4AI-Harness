"""Generate SQL, execute it, classify any failure as syntax / schema / semantics, then apply a class-specific repair for up to 2 rounds."""

import difflib
import re

from .. import bridge
from ..harness_base import SQLHarness


class P2P2DKimiS2ErrorClassify(SQLHarness):
    """Execution-feedback harness around a frozen weak Text-to-SQL solver.

    Control flow implemented by solve():
      1. Generate one SQL query greedily with the frozen LLM.
      2. Execute it via self.execute().
      3. On failure, classify the failure into exactly one bucket:
           - "syntax"    : the engine cannot parse the query,
           - "schema"    : the query names tables/columns absent from the schema,
           - "semantics" : names parse and exist, but the logic does not answer
                           the question (empty result set or residual runtime error).
      4. Dispatch to the matching strategy (_repair_syntax / _repair_schema /
         _repair_semantics) and loop, for at most MAX_REPAIR_ROUNDS repairs.
    """

    MAX_REPAIR_ROUNDS = 2

    SYNTAX = "syntax"
    SCHEMA = "schema"
    SEMANTICS = "semantics"

    # ------------------------------------------------------------------ control flow
    def solve(self, question: str) -> str:
        sql = self._generate_initial_sql(question)
        last_executable_sql = None

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            result = self._safe_execute(sql)

            if result["ok"] and result["rows"]:
                return sql                        # success: non-empty result
            if result["ok"]:
                last_executable_sql = sql         # runs but empty -> semantics issue
            if round_idx == self.MAX_REPAIR_ROUNDS:
                break                             # repair budget exhausted

            failure_class = self._classify_failure(sql, result)
            try:
                if failure_class == self.SYNTAX:
                    sql = self._repair_syntax(question, sql, result)
                elif failure_class == self.SCHEMA:
                    sql = self._repair_schema(question, sql, result)
                else:
                    sql = self._repair_semantics(question, sql, result)
            except Exception:
                pass                              # keep pre-repair SQL if a fix blows up

        # Prefer a query that at least executed; otherwise return the last attempt.
        return last_executable_sql if last_executable_sql is not None else sql

    # ------------------------------------------------------------------ generation
    def _generate_initial_sql(self, question: str) -> str:
        prompt = (
            "You are given a SQLite database schema and a natural-language question.\n"
            "Write ONE SQLite query that answers the question.\n\n"
            "### Database schema\n" + (self.schema or "") + "\n\n"
            "### Question\n" + question + "\n\n"
            "Rules:\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- Output only the SQL query, with no explanation and no markdown.\n\n"
            "SQL:"
        )
        try:
            raw = self._call_llm(
                prompt,
                system="You are a precise Text-to-SQL engine.",
                temperature=0.0,
            )
        except Exception:
            raw = ""
        sql = bridge.extract_sql(raw)
        sql = sql if sql else (raw or "").strip()
        return sql if sql else "SELECT 1"

    # ------------------------------------------------------------------ classification
    _SCHEMA_SIGNALS = (
        "no such column", "no such table", "unknown column", "unknown table",
        "ambiguous column", "does not exist", "undefined column", "undefined table",
        "no column named", "invalid column name", "invalid object name",
    )
    _SYNTAX_SIGNALS = (
        "syntax error", "syntax", "unrecognized token", "parse error",
        "unbalanced", "unexpected token", "incomplete input",
        "unterminated string", "no such function",
    )

    def _classify_failure(self, sql: str, result: dict) -> str:
        """Route the failure to exactly one repair strategy."""
        # Executed but produced zero rows -> the logic, not the form, is wrong.
        if result["ok"]:
            return self.SEMANTICS
        error = (result["error"] or "").lower()
        # Schema errors are the most specific; check them first.
        for signal in self._SCHEMA_SIGNALS:
            if signal in error:
                return self.SCHEMA
        for signal in self._SYNTAX_SIGNALS:
            if signal in error:
                return self.SYNTAX
        # Unknown engine error: use the LLM as a tie-breaker, then route in control flow.
        return self._llm_classify_failure(sql, result["error"] or "")

    def _llm_classify_failure(self, sql: str, error: str) -> str:
        prompt = (
            "A SQL query failed. Classify the ROOT CAUSE into exactly one category:\n"
            "syntax    - malformed SQL grammar (the engine cannot parse it)\n"
            "schema    - references tables/columns/functions absent from the schema\n"
            "semantics - parses and names exist, but the logic cannot answer the question\n\n"
            "### Database schema\n" + (self.schema or "") + "\n\n"
            "### SQL\n" + sql + "\n\n"
            "### Engine error\n" + error + "\n\n"
            "Answer with one word only: syntax, schema, or semantics."
        )
        try:
            out = self._call_llm(prompt, system="You are a SQL error classifier.", temperature=0.0)
        except Exception:
            return self.SEMANTICS
        out = (out or "").strip().lower()
        for label in (self.SYNTAX, self.SCHEMA, self.SEMANTICS):
            if re.search(r"\b" + label + r"\b", out):
                return label
        return self.SEMANTICS

    # ------------------------------------------------------------------ repair: syntax
    def _repair_syntax(self, question: str, sql: str, result: dict) -> str:
        """Deterministic grammar cleanup, then a constrained LLM grammar-only rewrite."""
        cleaned = self._deterministic_syntax_cleanup(sql)
        prompt = (
            "The following SQLite query is SYNTACTICALLY INVALID.\n\n"
            "### Database schema\n" + (self.schema or "") + "\n\n"
            "### Question\n" + question + "\n\n"
            "### Invalid SQL\n" + cleaned + "\n\n"
            "### Engine error\n" + (result["error"] or "") + "\n\n"
            "Fix ONLY the grammar (parentheses, quoting, commas, keywords, clause order); "
            "preserve the original intent and the schema identifiers.\n"
            "Output only the corrected SQL query."
        )
        raw = self._call_llm(prompt, system="You repair malformed SQLite queries.", temperature=0.0)
        repaired = bridge.extract_sql(raw)
        return repaired if repaired else cleaned

    @staticmethod
    def _deterministic_syntax_cleanup(sql: str) -> str:
        s = (sql or "").strip()
        # Strip markdown fences if any slipped past extraction.
        s = re.sub(r"^