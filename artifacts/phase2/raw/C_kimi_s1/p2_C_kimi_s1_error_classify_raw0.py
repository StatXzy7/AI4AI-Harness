"""Error-classifying Text-to-SQL harness: generate SQL, execute it, classify each failure as syntax / schema / semantics, and apply a class-specific repair for up to two repair rounds."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS1ErrorClassify(SQLHarness):
    """Generate -> execute -> classify -> targeted-repair loop.

    Round 0 generates an initial query. Every failed execution is classified
    into one of three failure classes from the database error message:

      * ``syntax``    - the SQL cannot be parsed;
      * ``schema``    - the SQL references missing/ambiguous tables or columns;
      * ``semantics`` - anything else (runtime errors) or an empty result set.

    Each class triggers a different repair strategy (deterministic cleanup +
    constrained rewrite for syntax, identifier re-grounding against the schema
    for schema errors, and full re-derivation from the question for semantic
    errors). At most ``MAX_REPAIR_ROUNDS`` repairs are attempted, and a query
    that at least executes is always preferred as the fallback answer.
    """

    MAX_REPAIR_ROUNDS = 2

    _SCHEMA_MARKERS = (
        "no such table",
        "no such column",
        "no column named",
        "unknown column",
        "unknown table",
        "column not found",
        "table not found",
        "does not exist",
        "invalid identifier",
        "ambiguous column",
        "no such function",
        "unknown function",
        "unknown identifier",
    )

    _SYNTAX_MARKERS = (
        "syntax error",
        "syntaxerror",
        " near ",
        "unrecognized token",
        "unexpected token",
        "parse error",
        "incomplete input",
        "unterminated",
        "mismatched input",
        "incorrect syntax",
        "expected expression",
    )

    # ------------------------------------------------------------------ API
    def solve(self, question: str) -> str:
        sql = self._initial_sql(question)
        executable_fallback = None  # last SQL that at least executed
        seen = {self._norm(sql)}

        for attempt in range(self.MAX_REPAIR_ROUNDS + 1):
            result = self._safe_execute(sql)

            if result.get("ok"):
                rows = result.get("rows") or []
                if rows:
                    return sql
                # Executed but empty -> suspicious, treat as a semantic failure.
                executable_fallback = sql
                if attempt >= self.MAX_REPAIR_ROUNDS:
                    return sql
                repaired = self._repair(
                    "semantics",
                    question,
                    sql,
                    note=(
                        "It executed successfully but returned 0 rows, which is "
                        "suspicious: the filters may be too restrictive, use "
                        "wrong literal values, or join the wrong keys."
                    ),
                )
                if repaired and self._norm(repaired) not in seen:
                    sql = repaired
                    seen.add(self._norm(repaired))
                continue

            error = (result.get("error") or "").strip() or "unknown execution error"
            if attempt >= self.MAX_REPAIR_ROUNDS:
                break

            # --- classify the failure and apply the class-specific fix ---
            failure_class = self._classify_error(error)
            repaired = self._repair(failure_class, question, sql, error=error)

            if not repaired or self._norm(repaired) in seen:
                # The targeted fix stalled; escalate to a full semantic re-derivation.
                repaired = self._repair(
                    "semantics",
                    question,
                    sql,
                    error=error,
                    note=(
                        "The previous class-specific fix produced no change, so "
                        "re-derive the whole query from the question instead."
                    ),
                )
            if repaired and self._norm(repaired) not in seen:
                sql = repaired
                seen.add(self._norm(repaired))

        return executable_fallback if executable_fallback is not None else sql

    # ---------------------------------------------------------- generation
    def _initial_sql(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL engine. Given a database schema and a "
            "natural-language question, write a single SQL query that answers it. "
            "Output only the SQL query."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. Use only tables and "
            "columns that appear in the schema. Output only the SQL query."
        )
        sql = self._extract(self.llm(prompt, system=system, temperature=0.0))
        return sql or "SELECT 1"

    # -------------------------------------------------------- classification
    def _classify_error(self, error: str) -> str:
        """Map a database error message to 'syntax', 'schema' or 'semantics'."""
        e = f" {error.lower()} "
        if any(marker in e for marker in self._SCHEMA_MARKERS):
            return "schema"
        if any(marker in e for marker in self._SYNTAX_MARKERS):
            return "syntax"
        return "semantics"

    # -------------------------------------------------------------- repairs
    def _repair(self, failure_class: str, question: str, sql: str,
                error: str = "", note: str = "") -> str:
        if failure_class == "syntax":
            return self._fix_syntax(question, sql, error)
        if failure_class == "schema":
            return self._fix_schema(question, sql, error)
        return self._fix_semantics(question, sql, error, note)

    def _fix_syntax(self, question: str, sql: str, error: str) -> str:
        base = self._light_syntax_cleanup(sql)
        system = (
            "You are a SQL syntax corrector. You fix only syntax and never "
            "change identifiers or query logic. Output only SQL."
        )
        prompt = (
            "The following SQL query failed with a SYNTAX error.\n\n"
            f"Question:\n{question}\n\n"
            f"Broken SQL:\n{base}\n\n"
            f"Database error:\n{error[:500]}\n\n"
            f"Database schema:\n{self.schema}\n\n"
            "Repair ONLY the syntax (keywords, clause order, commas, "
            "parentheses, quoting, semicolons). Keep every table name, column "
            "name, join, filter and aggregation exactly as intended. "
            "Output only the corrected SQL query."
        )
        fixed = self._extract(self.llm(prompt, system=system, temperature=0.0))
        if fixed and self._norm(fixed) != self._norm(sql):
            return fixed
        if self._norm(base) != self._norm(sql):
            return base  # deterministic cleanup alone changed something
        return fixed or sql

    def _fix_schema(self, question: str, sql: str, error: str) -> str:
        offender = self._extract_offending_identifier(error)
        offender_line = (
            f"\nThe offending identifier reported by the database is: {offender}\n"
            if offender else ""
        )
        system = (
            "You are a SQL re-grounding expert. You rewrite queries so every "
            "identifier exactly matches the given schema. Output only SQL."
        )
        prompt = (
            "The following SQL query failed because it references a table or "
            "column that does not exist (or is ambiguous).\n\n"
            f"Question:\n{question}\n\n"
            f"Broken SQL:\n{sql}\n\n"
            f"Database error:\n{error[:500]}\n"
            f"{offender_line}\n"
            f"Database schema (the ONLY valid tables and columns):\n{self.schema}\n\n"
            "Rewrite the query so that every table and column name exactly "
            "matches the schema above. Map the offending identifier to the "
            "closest valid name from the schema (fix typos, wrong table "
            "prefixes, or invented names), qualify ambiguous columns with "
            "their table, and keep the question's intent unchanged. "
            "Output only the corrected SQL query."
        )
        fixed = self._extract(self.llm(prompt, system=system, temperature=0.0))
        return fixed or sql

    def _fix_semantics(self, question: str, sql: str, error: str = "",
                       note: str = "") -> str:
        reason = note or (
            f"It failed at runtime with: {error[:300]}" if error
            else "Its result is likely wrong."
        )
        system = (
            "You are a careful Text-to-SQL reasoner. You re-derive queries "
            "from the question when the current query answers it incorrectly. "
            "Output only SQL."
        )
        prompt = (
            "The following SQL query is syntactically valid and uses valid "
            "schema objects, but it does NOT correctly answer the question.\n"
            f"{reason}\n\n"
            f"Question:\n{question}\n\n"
            f"Current SQL:\n{sql}\n\n"
            f"Database schema:\n{self.schema}\n\n"
            "Re-read the question and re-derive the query from scratch:\n"
            "- choose the tables/columns that match the entities in the question,\n"
            "- verify the JOIN keys actually connect the chosen tables,\n"
            "- check filter values and comparison operators against the wording,\n"
            "- check aggregation, GROUP BY, HAVING, ORDER BY, DISTINCT and LIMIT.\n"
            "Output only the corrected SQL query."
        )
        fixed = self._extract(self.llm(prompt, system=system, temperature=0.2))
        return fixed or sql

    # ------------------------------------------------------------- helpers
    def _extract(self, text) -> str:
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""
        if not sql:
            sql = text or ""
        return str(sql).strip()

    def _safe_execute(self, sql: str) -> dict:
        try:
            return self.execute(sql)
        except Exception as exc:  # the executor itself blew up
            return {"ok": False, "rows": [], "error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _norm(sql: str) -> str:
        return re.sub(r"\s+", " ", (sql or "").strip().rstrip(";")).lower()

    @staticmethod
    def _light_syntax_cleanup(sql: str) -> str:
        s = (sql or "").strip()
        # Drop markdown fences / language tags that survived extraction.
        lines = [ln for ln in s.splitlines() if not ln.strip().startswith("