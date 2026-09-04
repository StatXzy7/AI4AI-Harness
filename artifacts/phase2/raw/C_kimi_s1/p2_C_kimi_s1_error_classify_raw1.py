"""Generate SQL, execute it, classify any failure as syntax/schema/semantics from the database error, and apply a class-specific repair strategy for up to two rounds."""

import difflib
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS1ErrorClassify(SQLHarness):
    """Error-classification repair harness for Text-to-SQL.

    Control flow:
      1. Generate an initial SQL query from (schema, question) and execute it.
      2. If execution fails -- or succeeds with an empty result -- classify the
         failure IN CODE using the database error message:
             * syntax    : malformed SQL text
             * schema    : nonexistent / ambiguous identifiers
             * semantics : well-formed but logically wrong (incl. 0 rows)
      3. Dispatch to a strategy-specific repair (different prompt + different
         guidance per class; schema repair additionally suggests real
         identifiers via fuzzy matching against the parsed schema).
      4. At most MAX_REPAIRS repair rounds. The first query that executed
         successfully is preferred as the final answer (so a repair never
         makes the result worse).
    """

    MAX_REPAIRS = 2

    _REPAIR_SYSTEM = (
        "You are a precise SQL repair engine. "
        "Return exactly one corrected SQL query and nothing else."
    )

    # Order matters: schema errors are checked before syntax errors.
    _SCHEMA_ERROR_PATTERNS = (
        r"no such column",
        r"no such table",
        r"no such function",
        r"ambiguous column",
        r"unknown column",
        r"unknown table",
        r"has no column named",
        r"invalid column name",
        r"invalid object name",
        r"column .+ does not exist",
        r"table .+ does not exist",
    )

    _SYNTAX_ERROR_PATTERNS = (
        r"syntax error",
        r"error in your sql syntax",
        r"unrecognized token",
        r"incomplete input",
        r"unterminated",
        r"unbalanced",
        r"parse error",
        r"unexpected token",
    )

    # ------------------------------------------------------------------ #
    # main loop                                                          #
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        sql = self._generate(question)
        best_ok = None                     # first SQL that executed cleanly
        seen = {self._norm(sql)}

        for attempt in range(self.MAX_REPAIRS + 1):
            result = self._safe_execute(sql)

            if result["ok"]:
                best_ok = sql
                if result["rows"]:
                    return sql             # success: rows returned
                failure_class = "semantics"  # ran but empty -> suspicious
            else:
                failure_class = self._classify_error(result["error"])

            if attempt >= self.MAX_REPAIRS:
                break

            fixed = self._repair(question, sql, result, failure_class)
            if not fixed or self._norm(fixed) in seen:
                break                      # no progress; don't burn rounds
            sql = fixed
            seen.add(self._norm(sql))

        return best_ok if best_ok is not None else sql

    # ------------------------------------------------------------------ #
    # generation / repair prompts                                        #
    # ------------------------------------------------------------------ #

    def _generate(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL engine. Given a database schema "
            "and a natural-language question, produce exactly one "
            "syntactically valid SQL query."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. "
            "Output the SQL only -- no explanation, no commentary."
        )
        text = self._call_llm(prompt, system)
        sql = bridge.extract_sql(text) or (text or "").strip()
        return sql if sql else "SELECT 1"

    def _repair(self, question: str, sql: str, result: dict, failure_class: str) -> str:
        if failure_class == "syntax":
            return self._repair_syntax(question, sql, result["error"])
        if failure_class == "schema":
            return self._repair_schema(question, sql, result["error"])
        return self._repair_semantics(question, sql, result)

    def _repair_syntax(self, question: str, sql: str, error: str) -> str:
        token_note = ""
        m = re.search(r'near\s+"([^"]+)"', error or "")
        if not m:
            m = re.search(r'unrecognized token:\s*"([^"]+)"', error or "")
        if m:
            token_note = (
                f'- The database located the problem near the token "{m.group(1)}".\n'
            )
        guidance = (
            "- This is a SYNTAX error: the query text is malformed.\n"
            "- Fix ONLY the syntax. Preserve the original tables, columns, "
            "predicates, and overall logic exactly.\n"
            "- Check: balanced parentheses and quotes, commas between SELECT "
            "items, valid keywords, and clause order "
            "SELECT -> FROM -> JOIN ... ON -> WHERE -> GROUP BY -> HAVING -> "
            "ORDER BY -> LIMIT.\n"
            f"{token_note}"
        )
        prompt = self._fix_prompt(question, sql, f"syntax error: {error}", guidance)
        return self._apply_llm_fix(prompt, sql)

    def _repair_schema(self, question: str, sql: str, error: str) -> str:
        missing = self._missing_identifier(error)
        parts = [
            "- This is a SCHEMA error: the query references a table, column, "
            "or function that does not exist in the schema, or an ambiguous "
            "column name.\n",
        ]
        if missing:
            parts.append(
                f'- The offending identifier reported by the database is "{missing}".\n'
            )
            tables, columns = self._schema_identifiers()
            pool = list(dict.fromkeys(columns + tables))
            close = difflib.get_close_matches(missing, pool, n=5, cutoff=0.35)
            if close:
                parts.append(
                    "- Closest matching real identifiers in the schema: "
                    + ", ".join(close)
                    + ".\n"
                )
        parts.append(
            "- Replace invalid identifiers with EXACT names from the schema "
            "above; qualify ambiguous columns with their table name; do not "
            "invent columns or tables.\n"
        )
        prompt = self._fix_prompt(question, sql, f"schema error: {error}", "".join(parts))
        return self._apply_llm_fix(prompt, sql)

    def _repair_semantics(self, question: str, sql: str, result: dict) -> str:
        if result["ok"]:
            issue = (
                "semantic error: the query executed successfully but returned "
                "0 rows, so its predicates are likely wrong or too restrictive"
            )
        else:
            issue = f"semantic/logic error reported by the database: {result['error']}"
        guidance = (
            "- This is a SEMANTIC error: the SQL is well-formed but its logic "
            "does not match the question.\n"
            "- Re-read the question and audit every WHERE predicate: value "
            "spelling, letter case, units, and whether the filtered column is "
            "the right one (prefer LIKE for uncertain string matches).\n"
            "- Check JOIN paths: join only the tables the question needs, on "
            "the correct key columns from the schema.\n"
            "- Aggregates belong in SELECT/HAVING, never in WHERE; every "
            "non-aggregated selected column must appear in GROUP BY.\n"
            "- If the query returned 0 rows, relax over-restrictive predicates "
            "while still answering the question precisely.\n"
        )
        prompt = self._fix_prompt(question, sql, issue, guidance)
        return self._apply_llm_fix(prompt, sql)

    def _fix_prompt(self, question: str, sql: str, issue: str, guidance: str) -> str:
        return (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"The following SQL query is incorrect:\n