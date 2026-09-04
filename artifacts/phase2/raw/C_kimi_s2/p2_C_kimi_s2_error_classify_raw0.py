"""Harness that generates SQL, executes it, classifies any failure in code as syntax / schema / semantics, and applies a class-specific repair strategy for up to two rounds."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2ErrorClassify(SQLHarness):
    """Error-classifying Text-to-SQL harness.

    Control flow:
      1. Generate an initial SQL query from (schema, question).
      2. Execute it against the database.
      3. On failure, classify the problem IN CODE (not in the prompt):
           - "syntax"    : the DB rejected the query text (parse/grammar).
           - "schema"    : the DB reported unknown/ambiguous identifiers.
           - "semantics" : the query executed but returned zero rows.
      4. Dispatch to a class-specific repair routine (distinct prompt,
         distinct extracted error evidence, distinct temperature).
      5. Allow at most MAX_REPAIR_ROUNDS repairs; at exhaustion, prefer
         the last executable query over one the database rejects.
    """

    MAX_REPAIR_ROUNDS = 2

    # Error-message signatures used by the classifier (checked in order:
    # schema first, so identifier errors are never swallowed by syntax).
    _SCHEMA_ERROR_PATTERNS = (
        "no such table",
        "no such column",
        "no such function",
        "ambiguous column",
        "unknown column",
        "unknown table",
        "no column named",
        "has no column",
        "no such",
    )
    _SYNTAX_ERROR_PATTERNS = (
        "syntax error",
        "unrecognized token",
        "incomplete input",
        "near ",
        "expected",
        "parse error",
    )

    # Pulls the offending identifier out of DB error messages, e.g.
    # "no such column: stadn" -> "stadn".
    _IDENTIFIER_RE = re.compile(
        r"no such (?:table|column|function)\s*:\s*([\w\".]+)"
        r"|ambiguous column name\s*:\s*([\w\".]+)",
        re.IGNORECASE,
    )

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        sql = self._initial_sql(question)

        last_executable_sql = None
        seen = {self._normalize(sql)}

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            result = self.execute(sql)

            if result.get("ok"):
                last_executable_sql = sql
                if result.get("rows"):
                    return sql  # success: executes and is non-empty

            failure_class = self._classify(result)

            if round_idx >= self.MAX_REPAIR_ROUNDS:
                break  # repair budget exhausted

            repaired = self._repair(question, sql, result, failure_class,
                                    round_idx)

            # Anti-stall: never re-execute a query we already tried; force
            # a more diverse regeneration of the same failure class, and
            # give up early if the model is stuck.
            if self._normalize(repaired) in seen:
                repaired = self._repair(question, sql, result, failure_class,
                                        round_idx, force_alternative=True)
                if self._normalize(repaired) in seen:
                    break

            seen.add(self._normalize(repaired))
            sql = repaired

        # A query that runs (even with an empty result) is a better final
        # answer than one the database rejects outright.
        return last_executable_sql if last_executable_sql is not None else sql

    # ------------------------------------------------------------------ #
    # failure classification -- control flow, not prompt
    # ------------------------------------------------------------------ #
    def _classify(self, result: dict) -> str:
        """Map an execution result to one of: syntax / schema / semantics."""
        if result.get("ok"):
            # Executed cleanly but produced zero rows -> the logic, not
            # the grammar or identifiers, is wrong.
            return "semantics"

        error = (result.get("error") or "").lower()

        if any(pat in error for pat in self._SCHEMA_ERROR_PATTERNS):
            return "schema"
        if any(pat in error for pat in self._SYNTAX_ERROR_PATTERNS):
            return "syntax"
        # Unrecognized DB error: default to the syntax strategy, which
        # rewrites the query conservatively instead of trusting its shape.
        return "syntax"

    # ------------------------------------------------------------------ #
    # strategy-specific repairs
    # ------------------------------------------------------------------ #
    def _repair(self, question, sql, result, failure_class, round_idx,
                force_alternative=False):
        if failure_class == "schema":
            return self._fix_schema(question, sql, result, force_alternative)
        if failure_class == "semantics":
            return self._fix_semantics(question, sql, result, round_idx,
                                       force_alternative)
        return self._fix_syntax(question, sql, result, force_alternative)

    def _fix_syntax(self, question, sql, result, force_alternative):
        """Strategy for grammar failures: preserve intent, fix form only."""
        error = result.get("error") or "unknown syntax error"
        prompt = (
            "The following SQLite query FAILED TO PARSE.\n\n"
            f"Failing query:\n{sql}\n\n"
            f"Database error:\n{error}\n\n"
            "Rewrite it as syntactically valid SQLite. Fix ONLY the grammar "
            "(parentheses, keywords, quoting, clause order, commas, alias "
            "usage); keep the tables, columns and overall logic identical "
            "unless they are the direct cause of the parse error.\n"
            "Return only the corrected SQL query.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}"
        )
        temperature = 0.4 if force_alternative else 0.0
        return self._ask(prompt, temperature=temperature)

    def _fix_schema(self, question, sql, result, force_alternative):
        """Strategy for identifier failures: re-ground on the schema."""
        error = result.get("error") or "unknown schema error"
        offenders = self._extract_offending_identifiers(error)
        offender_block = (
            "Offending identifier(s): " + ", ".join(offenders) + "\n\n"
            if offenders else ""
        )
        prompt = (
            "The following SQLite query references INVALID identifiers.\n\n"
            f"Failing query:\n{sql}\n\n"
            f"Database error:\n{error}\n\n"
            f"{offender_block}"
            "Repair it using ONLY table and column names that appear "
            "VERBATIM in the schema below. Map each bad identifier to its "
            "correct schema counterpart (check spelling, singular/plural, "
            "and which table actually owns the column). If a column is "
            "ambiguous, qualify it with its table name. Do not invent "
            "columns or tables.\n"
            "Return only the corrected SQL query.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}"
        )
        temperature = 0.4 if force_alternative else 0.0
        return self._ask(prompt, temperature=temperature)

    def _fix_semantics(self, question, sql, result, round_idx,
                       force_alternative):
        """Strategy for logic failures: the query runs but answers wrongly."""
        prompt = (
            "The following SQLite query EXECUTED but returned ZERO ROWS, "
            "so its logic does not match the data or the question.\n\n"
            f"Query:\n{sql}\n\n"
            "Diagnose and fix the LOGICAL error. Common causes:\n"
            "- WHERE filters that are too restrictive or on the wrong column\n"
            "- string literals with wrong case/format (prefer LIKE, or relax "
            "the predicate)\n"
            "- JOIN conditions on the wrong keys, silently dropping all rows\n"
            "- wrong aggregation, GROUP BY, HAVING, or ORDER BY/LIMIT choice\n"
            "- mutually contradictory conditions\n"
            "Re-read the question, align every condition with it, and produce "
            "a corrected query that returns the intended rows.\n"
            "Return only the corrected SQL query.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}"
        )
        # A repeated semantic failure gets a more diverse rewrite.
        temperature = 0.4 if (force_alternative or round_idx > 0) else 0.0
        return self._ask(prompt, temperature=temperature)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _initial_sql(self, question: str) -> str:
        prompt = (
            "Write a single SQLite SQL query that answers the question using "
            "only the tables and columns present in the schema.\n"
            "Return only the SQL query, with no explanation.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}"
        )
        return self._ask(prompt, temperature=0.0)

    def _ask(self, prompt: str, temperature: float = 0.0) -> str:
        text = self.llm(
            prompt,
            system="You are an expert SQLite query writer. Output only SQL.",
            temperature=temperature,
            n=1,
        )
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        sql = bridge.extract_sql(text)
        return sql if sql else str(text).strip()

    def _extract_offending_identifiers(self, error: str):
        found = []
        for match in self._IDENTIFIER_RE.finditer(error):
            ident = match.group(1) or match.group(2)
            if ident and ident not in found:
                found.append(ident)
        return found

    @staticmethod
    def _normalize(sql: str) -> str:
        return re.sub(r"\s+", " ", (sql or "").strip().rstrip(";")).lower()