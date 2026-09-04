"""Generates SQL, executes it, classifies failures as syntax/schema/semantics, and applies targeted fixes for up to two repair rounds."""
from ..harness_base import SQLHarness
from .. import bridge
import json


class P2P2DDeepseekS2ErrorClassify(SQLHarness):
    MAX_REPAIR_ROUNDS = 2

    def solve(self, question: str) -> str:
        sql = self._generate_sql(question)

        for _ in range(self.MAX_REPAIR_ROUNDS + 1):
            if not sql:
                sql = self._generate_sql(question)

            result = self.execute(sql)
            if not isinstance(result, dict):
                result = {"ok": False, "rows": [], "error": str(result)}

            if result.get("ok"):
                if self._is_semantically_valid(question, sql, result):
                    return sql
                sql = self._fix_semantics(question, sql, result)
            else:
                error = result.get("error", "")
                classification = self._classify_error(error)

                if classification == "syntax":
                    sql = self._fix_syntax(question, sql, error)
                elif classification == "schema":
                    sql = self._fix_schema(question, sql, error)
                else:
                    sql = self._fix_generic(question, sql, error)

        return sql

    def _generate_sql(self, question: str) -> str:
        prompt = (
            "You are given a database schema and a natural-language question.\n"
            "Write a single SQL query that correctly answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only the SQL query."
        )
        system = (
            "You are an expert SQL engineer. "
            "Use only tables and columns from the provided schema."
        )
        raw = self._call_llm(prompt, system=system)
        return self._extract_sql(raw)

    def _fix_syntax(self, question: str, sql: str, error: str) -> str:
        prompt = (
            "The following SQL query produced a syntax error.\n"
            "Fix the syntax while preserving the intended meaning.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Broken SQL:\n{sql}\n\n"
            f"Error:\n{error}\n\n"
            "Return only the corrected SQL query."
        )
        system = "You are an expert SQL syntax debugger. Return only SQL."
        raw = self._call_llm(prompt, system=system)
        return self._extract_sql(raw, fallback=sql)

    def _fix_schema(self, question: str, sql: str, error: str) -> str:
        prompt = (
            "The following SQL query references tables or columns that do not exist "
            "in the database schema.\n"
            "Rewrite the query using only the tables and columns listed in the schema.\n"
            "Preserve the intent of the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Broken SQL:\n{sql}\n\n"
            f"Error:\n{error}\n\n"
            "Return only the corrected SQL query."
        )
        system = (
            "You are an expert SQL schema debugger. "
            "Ground every table and column in the provided schema."
        )
        raw = self._call_llm(prompt, system=system)
        return self._extract_sql(raw, fallback=sql)

    def _fix_semantics(self, question: str, sql: str, result: dict) -> str:
        rows_str = self._format_rows(result.get("rows", []))
        prompt = (
            "The SQL query below executed successfully, but it may not correctly "
            "answer the question.\n"
            "Review the question, schema, SQL, and returned rows. Write a corrected "
            "SQL query that accurately answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"SQL:\n{sql}\n\n"
            f"Returned rows:\n{rows_str}\n\n"
            "Return only the final SQL query."
        )
        system = (
            "You are an expert SQL semantic debugger. "
            "Return only SQL that directly answers the question."
        )
        raw = self._call_llm(prompt, system=system)
        return self._extract_sql(raw, fallback=sql)

    def _fix_generic(self, question: str, sql: str, error: str) -> str:
        prompt = (
            "The following SQL query failed. Fix it based on the schema and question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Broken SQL:\n{sql}\n\n"
            f"Error:\n{error}\n\n"
            "Return only the corrected SQL query."
        )
        system = "You are an expert SQL debugger. Return only SQL."
        raw = self._call_llm(prompt, system=system)
        return self._extract_sql(raw, fallback=sql)

    def _classify_error(self, error: str) -> str:
        err = error.lower()

        syntax_markers = (
            "syntax error",
            "syntaxerror",
            "mismatched input",
            "unexpected token",
            "parse error",
            "incorrect syntax",
            "unterminated",
            "incomplete input",
            "error near",
            "syntax error at or near",
            "malformed",
            "missing keyword",
            "missing expression",
            "missing right parenthesis",
            "missing left parenthesis",
            "unexpected end",
            "unexpected character",
            "unrecognized token",
        )

        schema_markers = (
            "no such table",
            "no such column",
            "unknown column",
            "does not exist",
            "invalid object name",
            "invalid identifier",
            "table or view does not exist",
            "unable to resolve",
            "unknown table",
            "ambiguous column",
            "not a column",
            "column does not exist",
            "invalid column",
            "invalid table",
            "relation",
            "missing from-clause entry",
            "undefined table",
            "cannot find",
            "not found",
            "unrecognized column",
            "unknown field",
            "column not found",
            "table not found",
        )

        if any(m in err for m in syntax_markers):
            return "syntax"
        if any(m in err for m in schema_markers):
            return "schema"

        prompt = (
            "Classify this SQL execution error into exactly one category: syntax or schema.\n"
            "syntax means the SQL grammar is invalid.\n"
            "schema means the SQL references non-existent tables, columns, or aliases.\n\n"
            f"Error:\n{error}\n\n"
            "Return only one word: syntax or schema."
        )
        system = "You are a SQL error classifier. Return only syntax or schema."
        raw = self._call_llm(prompt, system=system).strip().lower()
        if "schema" in raw:
            return "schema"
        if "syntax" in raw:
            return "syntax"
        return "syntax"

    def _is_semantically_valid(self, question: str, sql: str, result: dict) -> bool:
        rows_str = self._format_rows(result.get("rows", []))
        prompt = (
            "You are a strict SQL reviewer. Given a database schema, a question, "
            "the SQL query, and the rows it returned, determine if the SQL correctly "
            "and completely answers the question.\n"
            "Consider whether the query returns wrong columns, wrong aggregation, "
            "wrong filters, too many rows, or an empty result when the question "
            "expects data. If any of these are true, answer NO.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"SQL:\n{sql}\n\n"
            f"Returned rows:\n{rows_str}\n\n"
            "Answer only YES or NO."
        )
        system = "You are an expert SQL reviewer. Answer only YES or NO."
        raw = self._call_llm(prompt, system=system).strip().upper()
        return raw.startswith("YES")

    def _call_llm(self, prompt: str, system: str = "") -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)

        if isinstance(response, str):
            return response.strip()

        if isinstance(response, list):
            if not response:
                return ""
            first = response[0]
            if isinstance(first, str):
                return first.strip()
            if isinstance(first, dict):
                return str(
                    first.get("text")
                    or first.get("content")
                    or first.get("completion")
                    or first
                ).strip()
            return str(first).strip()

        if isinstance(response, dict):
            for key in ("text", "content", "completion", "message", "output"):
                if response.get(key):
                    return str(response.get(key)).strip()
            return str(response).strip()

        if hasattr(response, "text"):
            return str(response.text).strip()
        if hasattr(response, "content"):
            return str(response.content).strip()

        return str(response).strip()

    def _extract_sql(self, text: str, fallback: str = "") -> str:
        if not text:
            return fallback

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        if extracted and extracted.strip():
            return extracted.strip()

        stripped = text.strip()
        if stripped.upper().startswith(("SELECT", "WITH")):
            return stripped

        return fallback if fallback else stripped

    def _format_rows(self, rows, limit: int = 10) -> str:
        if rows is None:
            return "(no rows returned)"

        try:
            data = list(rows)
        except Exception:
            return str(rows)

        if not data:
            return "(no rows returned)"

        try:
            return json.dumps(data[:limit], indent=2, default=str)
        except Exception:
            return str(data[:limit])