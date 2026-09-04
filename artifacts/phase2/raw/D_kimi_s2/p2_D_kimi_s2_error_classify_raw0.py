"""Generate SQL, execute it, classify each failure as syntax / schema / semantics in the control flow, and apply a class-specific repair for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2ErrorClassify(SQLHarness):
    """Error-classification harness over a frozen weak solver.

    Pipeline: draft SQL -> execute -> on failure classify the database error
    (syntax vs. schema vs. semantics) using string heuristics -> dispatch to a
    repair routine specialised for that failure class. At most two repair
    rounds are performed; a clean execution returning zero rows is treated as
    a semantic failure.
    """

    MAX_REPAIR_ROUNDS = 2

    SCHEMA_ERROR_MARKERS = (
        "no such table",
        "no such column",
        "no column named",
        "unknown column",
        "unknown table",
        "unknown database",
        "does not exist",
        "ambiguous column",
        "no such function",
    )
    SYNTAX_ERROR_MARKERS = (
        "syntax error",
        "unrecognized token",
        "unterminated string",
        "parse error",
        "mismatched input",
        "unexpected token",
        "near ",
    )

    # ------------------------------------------------------------------ solve
    def solve(self, question: str) -> str:
        sql = self._generate(question)

        for round_idx in range(self.MAX_REPAIR_ROUNDS + 1):
            result = self.execute(sql)

            if result.get("ok"):
                rows = result.get("rows") or []
                if rows or round_idx >= self.MAX_REPAIR_ROUNDS:
                    return sql
                # Ran cleanly but returned nothing: classify as a semantic failure.
                sql = self._repair_semantics(
                    question,
                    sql,
                    "The query executed without error but returned zero rows; "
                    "its filters, joins, or aggregation are likely wrong for the question.",
                )
                continue

            error = (result.get("error") or "").strip()
            if round_idx >= self.MAX_REPAIR_ROUNDS:
                break

            error_class = self._classify_error(error)
            if error_class == "syntax":
                sql = self._repair_syntax(question, sql, error)
            elif error_class == "schema":
                sql = self._repair_schema(question, sql, error)
            else:
                sql = self._repair_semantics(question, sql, error)

        return sql

    # ----------------------------------------------------------- classification
    def _classify_error(self, error: str) -> str:
        """Map a raw database error string to one of: syntax / schema / semantics."""
        e = error.lower()
        if any(marker in e for marker in self.SCHEMA_ERROR_MARKERS):
            return "schema"
        if any(marker in e for marker in self.SYNTAX_ERROR_MARKERS):
            return "syntax"
        return "semantics"

    # --------------------------------------------------------------- generation
    def _generate(self, question: str) -> str:
        prompt = (
            "You are given a SQLite database schema and a natural-language question.\n"
            "Write one syntactically valid SQLite query that answers the question.\n\n"
            f"=== Database schema ===\n{self.schema}\n\n"
            f"=== Question ===\n{question}\n\n"
            "Rules:\n"
            "- Output ONLY the SQL query: no explanation, no markdown fences.\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- Use SQLite dialect.\n"
        )
        raw = self.llm(
            prompt,
            system="You are an expert Text-to-SQL engine for SQLite.",
            temperature=0.0,
            n=1,
        )
        return bridge.extract_sql(raw)

    # ------------------------------------------------------------------ repairs
    def _repair_syntax(self, question: str, sql: str, error: str) -> str:
        """Syntax-class fix: correct grammar only, preserve the original logic."""
        prompt = (
            "The following SQLite query failed with a SYNTAX error. Fix ONLY the "
            "syntax; keep the original tables, columns, joins, filters and overall "
            "logic unchanged.\n\n"
            f"=== Database schema ===\n{self.schema}\n\n"
            f"=== Question ===\n{question}\n\n"
            f"=== Faulty query ===\n{sql}\n\n"
            f"=== Database error ===\n{error}\n\n"
            "Check for: unbalanced parentheses or quotes, missing commas, misplaced "
            "keywords, illegal clause order, unterminated string literals, and "
            "reserved words used as identifiers (quote those with double quotes).\n"
            "Output ONLY the corrected SQL query.\n"
        )
        raw = self.llm(
            prompt,
            system="You are a meticulous SQLite syntax corrector.",
            temperature=0.0,
            n=1,
        )
        fixed = bridge.extract_sql(raw)
        return fixed if fixed.strip() else sql

    def _repair_schema(self, question: str, sql: str, error: str) -> str:
        """Schema-class fix: re-ground invalid or ambiguous identifiers in the real schema."""
        prompt = (
            "The following SQLite query references tables or columns that do not "
            "exist, or that are ambiguous. Re-ground the query in the ACTUAL schema "
            "below: replace every invalid identifier with the closest matching table "
            "or column from the schema, and fully qualify ambiguous columns with "
            "their table name. Preserve the query's intent.\n\n"
            f"=== Database schema ===\n{self.schema}\n\n"
            f"=== Question ===\n{question}\n\n"
            f"=== Faulty query ===\n{sql}\n\n"
            f"=== Database error ===\n{error}\n\n"
            "Do NOT invent identifiers: every table and column in your answer must "
            "appear in the schema above.\n"
            "Output ONLY the corrected SQL query.\n"
        )
        raw = self.llm(
            prompt,
            system="You are an expert at aligning SQL queries with a database schema.",
            temperature=0.0,
            n=1,
        )
        fixed = bridge.extract_sql(raw)
        return fixed if fixed.strip() else sql

    def _repair_semantics(self, question: str, sql: str, error: str) -> str:
        """Semantics-class fix: re-derive the query logic from the question."""
        prompt = (
            "The following SQLite query is syntactically valid and uses valid "
            "schema identifiers, but it does NOT answer the question correctly.\n\n"
            f"=== Database schema ===\n{self.schema}\n\n"
            f"=== Question ===\n{question}\n\n"
            f"=== Wrong query ===\n{sql}\n\n"
            f"=== Observed problem ===\n{error}\n\n"
            "Re-read the question carefully and verify: the selected columns, the "
            "JOIN keys, the WHERE conditions and their literal values (they must "
            "match the question's wording), the aggregation function "
            "(COUNT/SUM/AVG/MAX/MIN), GROUP BY, ORDER BY direction, and LIMIT.\n"
            "Output ONLY the corrected SQL query.\n"
        )
        raw = self.llm(
            prompt,
            system="You are an expert at reasoning about the meaning of SQL queries.",
            temperature=0.0,
            n=1,
        )
        fixed = bridge.extract_sql(raw)
        return fixed if fixed.strip() else sql