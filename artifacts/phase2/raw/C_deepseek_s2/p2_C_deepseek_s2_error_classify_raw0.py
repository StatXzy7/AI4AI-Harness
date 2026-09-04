"""Classifies Text-to-SQL execution failures into syntax, schema, or semantics and applies targeted repair prompts for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS2ErrorClassify(SQLHarness):
    MAX_REPAIR_ROUNDS = 2

    SYNTAX_MARKERS = (
        "syntax error",
        "parse error",
        "near",
        "unexpected",
        "unrecognized",
        "incorrect syntax",
        "misuse",
        "error in your sql",
        "check the manual",
        "unclosed quotation",
        "unbalanced parenthesis",
        "syntax",
    )

    SCHEMA_MARKERS = (
        "no such table",
        "no such column",
        "unknown column",
        "unknown table",
        "relation",
        "does not exist",
        "not found",
        "invalid identifier",
        "ambiguous column",
        "cannot find",
        "unable to resolve",
        "unresolved",
        "missing from",
        "missing table",
        "invalid reference",
        "not a table",
        "not a column",
        "duplicate column",
        "can't find database",
        "unknow table",
        "invalid column name",
        "invalid table name",
        "column",
        "table",
    )

    def solve(self, question: str) -> str:
        schema = self.schema or ""
        sql = self._generate_initial(question, schema)

        for _ in range(self.MAX_REPAIR_ROUNDS):
            result = self._execute_safely(sql)

            if result.get("ok"):
                rows = result.get("rows") or []
                if rows:
                    return sql
                error_type = "semantics"
                error = "Query executed successfully but returned no rows."
            else:
                error = result.get("error", "Unknown error")
                error_type = self._classify_error(error)

            prompt = self._build_fix_prompt(question, sql, error_type, error, schema)
            fixed_raw = self._call_llm(
                prompt,
                system="You are a SQL repair assistant. Output only SQL.",
            )
            fixed_sql = self._extract_sql(fixed_raw) or sql

            # Avoid re-running the identical failing SQL; no progress would be made.
            if fixed_sql.strip().rstrip(";").strip() == sql.strip().rstrip(";").strip():
                continue
            sql = fixed_sql

        return sql

    def _generate_initial(self, question: str, schema: str) -> str:
        prompt = f"""You are an expert Text-to-SQL model.

Database schema:
{schema}

Question:
{question}

Write a single SQL query that answers the question. Output only SQL, no explanation.
"""
        raw = self._call_llm(
            prompt,
            system="You are an expert SQL developer. Output only SQL.",
        )
        return self._extract_sql(raw) or ""

    def _classify_error(self, error: str) -> str:
        e = (error or "").lower()
        if any(marker in e for marker in self.SYNTAX_MARKERS):
            return "syntax"
        if any(marker in e for marker in self.SCHEMA_MARKERS):
            return "schema"
        return "semantics"

    def _build_fix_prompt(
        self, question: str, sql: str, error_type: str, error: str, schema: str
    ) -> str:
        if error_type == "syntax":
            return f"""The SQL query below has a syntax error.

SQL: