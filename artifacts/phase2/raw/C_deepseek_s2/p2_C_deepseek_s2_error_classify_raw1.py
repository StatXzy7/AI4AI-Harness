"""Generate SQL, execute it, classify failures, and apply class-specific fixes for up to two rounds."""
from typing import Any, Dict, List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS2ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        sql = self._generate_initial_sql(question)

        for attempt in range(3):
            result = self._execute_safe(sql)
            if result.get("ok"):
                return sql

            if attempt == 2:
                break

            error = result.get("error", "")
            rows = result.get("rows", [])
            category = self._classify_failure(question, sql, error, rows)
            sql = self._fix_sql(question, sql, error, rows, category)

        return sql

    def _execute_safe(self, sql: str) -> Dict[str, Any]:
        try:
            return self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

    def _generate_initial_sql(self, question: str) -> str:
        prompt = (
            "You are an expert Text-to-SQL assistant. "
            "Given the database schema and a natural language question, write a single SQL query that answers the question.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only the SQL query."
        )
        return self._llm_to_sql(prompt)

    def _llm_to_sql(self, prompt: str) -> str:
        raw = self.llm(prompt) or ""
        try:
            extracted = bridge.extract_sql(raw)
        except Exception:
            extracted = raw

        if not extracted:
            return raw.strip()
        return extracted.strip()

    def _classify_failure(self, question: str, sql: str, error: str, rows: List[Any]) -> str:
        prompt = (
            "Classify the SQL failure for the following Text-to-SQL problem into exactly one of: syntax, schema, semantics.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Generated SQL:\n"
            f"{sql}\n\n"
            f"Execution error:\n{error or '(none)'}\n\n"
            f"Returned rows (if any):\n{rows}\n\n"
            "Output only one word: syntax, schema, or semantics."
        )

        response = (self.llm(prompt) or "").strip().lower()
        if "syntax" in response:
            return "syntax"
        if "schema" in response:
            return "schema"
        if "semantic" in response:
            return "semantics"

        err = error.lower()
        schema_markers = [
            "no such table",
            "no such column",
            "unknown column",
            "unknown table",
            "relation",
            "does not exist",
            "doesn't exist",
            "not exist",
            "column not found",
            "table not found",
            "invalid object name",
            "ambiguous column",
            "missing table",
            "missing column",
        ]
        syntax_markers = [
            "syntax error",
            "parse error",
            "syntaxerror",
            'near "',
            "near '",
            "unexpected token",
            "unexpected keyword",
            "unexpected end",
            "invalid syntax",
        ]

        if any(marker in err for marker in schema_markers):
            return "schema"
        if any(marker in err for marker in syntax_markers):
            return "syntax"

        return "semantics"

    def _fix_sql(self, question: str, sql: str, error: str, rows: List[Any], category: str) -> str:
        prompt = self._fix_prompt(question, sql, error, rows, category)
        return self._llm_to_sql(prompt)

    def _fix_prompt(self, question: str, sql: str, error: str, rows: List[Any], category: str) -> str:
        if category == "syntax":
            instruction = "Your previous SQL query had a syntax error. Fix the syntax and produce a valid SQL query."
        elif category == "schema":
            instruction = "Your previous SQL query referenced tables or columns that do not exist in the provided schema. Rewrite the query using only existing tables and columns."
        else:
            instruction = "Your previous SQL query did not correctly answer the question. Re-read the question and schema, then write a new SQL query that better captures the intended meaning."

        return (
            f"{instruction}\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Previous SQL:\n"
            f"{sql}\n\n"
            f"Execution error:\n{error or '(none)'}\n\n"
            f"Returned rows (if any):\n{rows}\n\n"
            "Return only the corrected SQL query."
        )