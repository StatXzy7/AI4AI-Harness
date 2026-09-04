"""Harness that generates SQL, executes it, classifies any failure as syntax / schema / semantics, and applies a class-specific repair for up to 2 rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS0ErrorClassify(SQLHarness):
    """Generate -> execute -> classify failure -> strategy-specific repair loop.

    The failure classifier and the per-class repair dispatch live in the harness
    control flow: rule-based error matching (with an LLM fallback) assigns one of
    {syntax, schema, semantics}, and each class triggers a distinct, dedicated
    repair strategy. At most 2 repair rounds are performed, then the best-effort
    SQL is returned.
    """

    MAX_REPAIR_ROUNDS = 2

    _SYNTAX_ERROR_HINTS = (
        "syntax error",
        "syntax",
        "parse error",
        "near ",
        "unexpected",
        "unrecognized token",
        "incomplete input",
        "mismatched input",
        "unterminated",
        "expected",
        "no such function",
        "wrong number of arguments",
    )

    _SCHEMA_ERROR_HINTS = (
        "no such table",
        "no such column",
        "unknown column",
        "unknown table",
        "unknown identifier",
        "does not exist",
        "undefined table",
        "undefined column",
        "no column named",
        "invalid column",
        "ambiguous column",
        "ambiguous",
        "unknown field",
    )

    # ------------------------------------------------------------------ main
    def solve(self, question: str) -> str:
        sql = self._generate_initial(question)
        last_runnable_sql = ""

        for _ in range(self.MAX_REPAIR_ROUNDS):
            result = self.execute(sql)

            if result.get("ok"):
                rows = result.get("rows") or []
                if rows:
                    return sql
                # Executed cleanly but returned 0 rows: candidate SEMANTIC
                # failure (over-restrictive filter, wrong join, etc.).
                last_runnable_sql = sql
                failure_class = "semantics"
                error_text = (
                    "The query executed successfully but returned 0 rows, so it "
                    "probably does not capture the intent of the question."
                )
            else:
                error_text = result.get("error") or "Unknown execution error."
                failure_class = self._classify_failure(question, sql, error_text)

            # Strategy-specific fix, dispatched on the failure class.
            sql = self._repair(question, sql, error_text, failure_class)

        # Final execution after the last repair round.
        result = self.execute(sql)
        if result.get("ok"):
            return sql
        return last_runnable_sql or sql

    # ----------------------------------------------------------- generation
    def _generate_initial(self, question: str) -> str:
        prompt = (
            "You are given the following database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. "
            "Output only the SQL query, with no explanations."
        )
        raw = self.llm(
            prompt,
            system="You are an expert Text-to-SQL system.",
            temperature=0.0,
            n=1,
        )
        text = raw if isinstance(raw, str) else str(raw)
        return self._extract_sql(text, fallback=text.strip())

    # --------------------------------------------------------- classification
    def _classify_failure(self, question: str, sql: str, error_text: str) -> str:
        """Return one of: 'syntax', 'schema', 'semantics'."""
        err = (error_text or "").lower()
        if any(hint in err for hint in self._SCHEMA_ERROR_HINTS):
            return "schema"
        if any(hint in err for hint in self._SYNTAX_ERROR_HINTS):
            return "syntax"
        # Error text is inconclusive: ask the LLM for the failure class.
        return self._llm_classify(question, sql, error_text)

    def _llm_classify(self, question: str, sql: str, error_text: str) -> str:
        prompt = (
            "A SQL query failed. Classify the root cause into exactly one category:\n"
            "- syntax: malformed SQL (grammar, keywords, clause order, parentheses, "
            "quoting, dialect).\n"
            "- schema: the query references tables or columns that do not exist, or "
            "uses ambiguous identifiers.\n"
            "- semantics: the SQL is valid but implements the wrong logic for the "
            "question (wrong tables, joins, filters, aggregation, or output shape).\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Failed SQL:\n{sql}\n\n"
            f"Database error: {error_text}\n\n"
            "Answer with exactly one word: syntax, schema, or semantics."
        )
        raw = self.llm(
            prompt,
            system="You are a precise SQL error classifier.",
            temperature=0.0,
            n=1,
        )
        text = (raw if isinstance(raw, str) else str(raw)).strip().lower()
        for label in ("syntax", "schema", "semantics"):
            if label in text:
                return label
        return "semantics"

    # ---------------------------------------------------------------- repair
    def _repair(self, question: str, sql: str, error_text: str, failure_class: str) -> str:
        fixers = {
            "syntax": self._fix_syntax,
            "schema": self._fix_schema,
            "semantics": self._fix_semantics,
        }
        fixer = fixers.get(failure_class, self._fix_semantics)
        return fixer(question, sql, error_text)

    def _fix_syntax(self, question: str, sql: str, error_text: str) -> str:
        """Syntax strategy: repair grammar only; freeze tables, columns, and logic."""
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"The following SQL query has a SYNTAX error:\n{sql}\n\n"
            f"Database error message: {error_text}\n\n"
            "Fix ONLY the syntax (keywords, clause order, parentheses, commas, "
            "quoting, operators, SQL dialect). Do NOT change the tables, columns, "
            "joins, filters, or aggregation logic. Output only the corrected SQL query."
        )
        raw = self.llm(
            prompt,
            system="You are a SQL syntax corrector.",
            temperature=0.0,
            n=1,
        )
        return self._extract_sql(raw, fallback=sql)

    def _fix_schema(self, question: str, sql: str, error_text: str) -> str:
        """Schema strategy: re-map every identifier to the actual schema."""
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"The following SQL query failed with a SCHEMA error (it references "
            f"tables or columns that do not exist, or uses ambiguous identifiers):\n{sql}\n\n"
            f"Database error message: {error_text}\n\n"
            "Rewrite the query so that every table name and column name exactly "
            "matches the schema above, and add explicit table qualifiers wherever "
            "a column name is ambiguous. Preserve the original query intent and "
            "logic. Output only the corrected SQL query."
        )
        raw = self.llm(
            prompt,
            system="You are a SQL schema-alignment corrector.",
            temperature=0.0,
            n=1,
        )
        return self._extract_sql(raw, fallback=sql)

    def _fix_semantics(self, question: str, sql: str, error_text: str) -> str:
        """Semantics strategy: rethink the query logic against the question."""
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"The following SQL query is syntactically valid and uses valid "
            f"identifiers, but it does NOT correctly answer the question "
            f"(a semantic / logic problem):\n{sql}\n\n"
            f"Observed problem: {error_text}\n\n"
            "Re-read the question carefully and rewrite the query with the correct "
            "logic: verify the chosen tables, join conditions, WHERE filters, "
            "GROUP BY / aggregation, ORDER BY / LIMIT, and any subqueries. "
            "Output only the corrected SQL query."
        )
        raw = self.llm(
            prompt,
            system="You are a SQL semantics corrector.",
            temperature=0.0,
            n=1,
        )
        return self._extract_sql(raw, fallback=sql)

    # ---------------------------------------------------------------- helpers
    def _extract_sql(self, raw, fallback: str = "") -> str:
        text = raw if isinstance(raw, str) else str(raw)
        try:
            candidate = bridge.extract_sql(text)
        except Exception:
            candidate = ""
        if candidate and candidate.strip():
            return candidate.strip()
        return fallback