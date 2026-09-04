"""Generates SQL, executes it, classifies failures as syntax/schema/semantics, and applies class-specific fixes for up to two repair rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS2ErrorClassify(SQLHarness):
    MAX_ROUNDS = 2

    _SYNTAX_HINTS = (
        "syntax error",
        "incomplete input",
        "unrecognized token",
        "malformed",
        "parse error",
        "unexpected",
        "expected",
        "near",
        "unclosed",
        "unterminated",
        "invalid token",
        "syntax",
    )

    _SCHEMA_HINTS = (
        "no such table",
        "no such column",
        "unknown column",
        "unknown table",
        "does not exist",
        "table not found",
        "column not found",
        "has no column named",
        "relation does not exist",
        "field not found",
        "ambiguous column",
        "ambiguous table",
        "schema",
    )

    _SEMANTIC_HINTS = (
        "semantic",
        "logic",
        "datatype mismatch",
        "type mismatch",
        "invalid use",
        "misuse",
        "aggregate",
        "group by",
        "not allowed",
        "wrong number",
        "argument",
        "constraint",
        "not null",
        "foreign key",
        "unique constraint",
        "check constraint",
        "division by zero",
        "overflow",
        "out of range",
        "recursive",
        "too complex",
        "too many",
    )

    def solve(self, question: str) -> str:
        question = str(question or "").strip()

        sql = self._generate_initial_sql(question)
        if not sql:
            return ""

        best_sql = sql
        result = self._execute_safe(sql)

        if result.get("ok"):
            return sql

        for _ in range(self.MAX_ROUNDS):
            category = self._classify_failure(question, sql, result)
            candidate = self._repair_sql(question, sql, result, category)

            if not candidate or self._same_query(candidate, sql):
                break

            sql = candidate
            best_sql = sql
            result = self._execute_safe(sql)

            if result.get("ok"):
                return sql

        return best_sql

    def _generate_initial_sql(self, question):
        prompt = (
            "Use the schema to answer the question.\n\n"
            f"Schema:\n{self._schema_text()}\n\n"
            f"Question:\n{question}\n\n"
            "Return only one executable SQL query."
        )
        raw = self._llm_text(
            prompt,
            system="You are an expert text-to-SQL engine. Output only SQL.",
        )
        return self._extract_sql(raw)

    def _repair_sql(self, question, sql, result, category):
        if category == "syntax":
            return self._fix_syntax(question, sql, result)
        if category == "schema":
            return self._fix_schema(question, sql, result)
        return self._fix_semantics(question, sql, result)

    def _fix_syntax(self, question, sql, result):
        prompt = (
            "The following SQL query failed with a syntax error.\n\n"
            f"Question:\n{question}\n\n"
            f"Schema:\n{self._schema_text()}\n\n"
            f"SQL:\n{sql}\n\n"
            f"Error:\n{result.get('error') or ''}\n\n"
            "Fix only the syntax while preserving the intended tables, columns, filters, and logic.\n"
            "Return only one corrected SQL query."
        )
        raw = self._llm_text(
            prompt,
            system="You are an expert SQL debugger. Output only SQL.",
        )
        return self._extract_sql(raw)

    def _fix_schema(self, question, sql, result):
        prompt = (
            "The following SQL query failed because it references incorrect schema objects.\n\n"
            f"Question:\n{question}\n\n"
            f"Schema:\n{self._schema_text()}\n\n"
            f"SQL:\n{sql}\n\n"
            f"Error:\n{result.get('error') or ''}\n\n"
            "Use only tables and columns that exist in the schema. Correct names, aliases, and qualifications.\n"
            "Return only one corrected SQL query."
        )
        raw = self._llm_text(
            prompt,
            system="You are an expert SQL schema mapper. Output only SQL.",
        )
        return self._extract_sql(raw)

    def _fix_semantics(self, question, sql, result):
        prompt = (
            "The following SQL query is syntactically acceptable but semantically wrong "
            "or produced a semantic/runtime failure.\n\n"
            f"Question:\n{question}\n\n"
            f"Schema:\n{self._schema_text()}\n\n"
            f"SQL:\n{sql}\n\n"
            f"Error:\n{result.get('error') or ''}\n\n"
            "Rewrite the query logic to match the question: correct tables, joins, filters, "
            "aggregations, grouping, ordering, and limits.\n"
            "Return only one corrected SQL query."
        )
        raw = self._llm_text(
            prompt,
            system="You are an expert SQL semantic repairer. Output only SQL.",
        )
        return self._extract_sql(raw)

    def _classify_failure(self, question, sql, result):
        error = str(result.get("error") or "").lower()

        if self._contains_any(error, self._SYNTAX_HINTS):
            return "syntax"
        if self._contains_any(error, self._SCHEMA_HINTS):
            return "schema"
        if self._contains_any(error, self._SEMANTIC_HINTS):
            return "semantics"

        llm_category = self._llm_classify_failure(question, sql, result)
        if llm_category:
            return llm_category

        if result.get("ok"):
            return "semantics"
        if "no such" in error or "unknown" in error or "does not exist" in error:
            return "schema"
        if "parse" in error or "token" in error or "incomplete" in error:
            return "syntax"
        return "semantics"

    def _llm_classify_failure(self, question, sql, result):
        prompt = (
            "Classify the SQL failure as syntax, schema, or semantics.\n\n"
            f"Question:\n{question}\n\n"
            f"Schema:\n{self._schema_text()}\n\n"
            f"SQL:\n{sql}\n\n"
            f"Execution error:\n{result.get('error') or ''}\n\n"
            "Definitions:\n"
            "- syntax: the SQL text cannot be parsed.\n"
            "- schema: the SQL references tables/columns that are missing or misspelled.\n"
            "- semantics: the SQL parses and references schema but has wrong logic or a runtime semantic problem.\n\n"
            "Answer with exactly one word: syntax, schema, or semantics."
        )
        raw = self._llm_text(
            prompt,
            system="You are a SQL error classifier. Answer with one word only.",
        ).strip().lower()

        for category in ("syntax", "schema", "semantics"):
            if category in raw:
                return category
        return ""

    def _execute_safe(self, sql):
        try:
            raw = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(raw, dict):
            rows = raw.get("rows", [])
            if rows is None:
                rows = []
            return {
                "ok": bool(raw.get("ok", False)),
                "rows": rows,
                "error": str(raw.get("error") or ""),
            }

        if isinstance(raw, bool):
            return {"ok": raw, "rows": [], "error": "" if raw else "execution failed"}

        return {"ok": False, "rows": [], "error": str(raw)}

    def _extract_sql(self, text):
        text = self._coerce_text(text)
        if not text:
            return ""

        extracted = None
        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = None

        extracted = self._coerce_text(extracted)
        if extracted:
            return self._clean_sql(extracted)

        if self._looks_like_sql(text):
            return self._clean_sql(text)

        return ""

    def _clean_sql(self, sql):
        sql = str(sql or "").strip()
        if not sql:
            return ""

        sql = self._strip_markdown(sql)

        while sql.endswith(";"):
            sql = sql[:-1].rstrip()

        return sql

    def _strip_markdown(self, sql):
        sql = sql.strip()
        if not sql.startswith("