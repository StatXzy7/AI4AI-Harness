"""Wraps a frozen weak SQL solver with classify-and-fix retry that distinguishes syntax, schema, and semantic errors to apply targeted repairs over up to two rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        # Round 0: initial generation
        sql = self._generate(question, hint="")
        attempt = 0
        max_rounds = 2

        while attempt <= max_rounds:
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            err = result.get("error", "") or ""
            category = self._classify_error(err)

            if attempt == max_rounds:
                # No more retries left
                return sql

            # Strategy-specific fix per category
            if category == "syntax":
                repaired = self._repair_syntax(question, sql, err)
            elif category == "schema":
                repaired = self._repair_schema(question, sql, err)
            else:  # semantics (default)
                repaired = self._repair_semantics(question, sql, err)

            if repaired == sql:
                # No progress; avoid infinite loop
                return sql
            sql = repaired
            attempt += 1

        return sql

    # ---------- Generation ----------
    def _generate(self, question: str, hint: str) -> str:
        system = (
            "You are a SQL generator. Output exactly one SQL statement "
            "for the given question against the provided schema. "
            "Return only the SQL, no prose or markdown fences."
        )
        user = f"Schema:\n{self.schema}\n\nQuestion: {question}\n"
        if hint:
            user += f"\nHints:\n{hint}\n"
        user += "\nSQL:"
        raw = self.llm(user, system=system, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)
        return sql or raw.strip()

    # ---------- Classification ----------
    def _classify_error(self, err: str) -> str:
        e = err.lower()
        # Syntax: parser/tokenizer complaints
        syntax_keys = (
            "syntax error", "syntax", "parse error", "unexpected",
            "near \"", "near '", "token", "unterminated", "mismatched",
            "invalid input syntax", "ora-", "you have an error in your sql",
            "malformed", "expected"
        )
        # Schema: missing/unknown columns or tables
        schema_keys = (
            "no such column", "unknown column", "undefined column",
            "no such table", "undefined table", "relation",
            "table not found", "column not found", "does not exist",
            "ambiguous column", "ambiguous reference",
            "schema", "invalid identifier", "unknown field",
            "table", "column"
        )
        if any(k in e for k in syntax_keys):
            return "syntax"
        if any(k in e for k in schema_keys):
            return "schema"
        # Default: treat as semantic (empty result / wrong answer / runtime)
        return "semantics"

    # ---------- Repairs ----------
    def _repair_syntax(self, question: str, sql: str, err: str) -> str:
        hint = (
            f"The previous SQL failed with a SYNTAX error: {err}\n"
            "Fix the syntax. Common issues: missing commas, unbalanced quotes, "
            "trailing punctuation, unmatched parentheses, reserved-word usage, "
            "or wrong statement terminators. Output only the corrected SQL."
        )
        return self._generate(question, hint=hint)

    def _repair_schema(self, question: str, sql: str, err: str) -> str:
        # Forcefully remind the model about the exact schema identifiers
        hint = (
            f"The previous SQL failed with a SCHEMA error: {err}\n"
            "Re-check every table and column name against the schema below. "
            "Use only tables and columns that exist exactly as written "
            "(respect case). Add table aliases and qualify columns with the "
            "correct table prefix if names are ambiguous.\n\n"
            f"Schema:\n{self.schema}\n"
        )
        return self._generate(question, hint=hint)

    def _repair_semantics(self, question: str, sql: str, err: str) -> str:
        hint = (
            f"The previous SQL ran without error but is likely incorrect "
            f"(error or empty/wrong result: {err}).\n"
            "Rewrite it so that it correctly answers the question. "
            "Re-read the question carefully: ensure the correct tables are "
            "joined, filters/aggregations match the question's intent, "
            "GROUP BY includes all selected non-aggregated columns, ORDER BY "
            "and LIMIT are applied only if needed, and use the proper join "
            "types. Output only the corrected SQL."
        )
        return self._generate(question, hint=hint)