"""Generate SQL, execute it, classify failures as syntax, schema, or semantics, and apply a class-specific repair prompt for up to two rounds."""
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS0ErrorClassify(SQLHarness):
    SYNTAX_PATTERNS = [
        r"syntax error",
        r"parse error",
        r"unexpected token",
        r"unexpected character",
        r"unexpected end",
        r"unterminated",
        r"malformed",
        r"could not parse",
        r"cannot parse",
        r"can't parse",
        r"not a valid sql",
        r"incorrect syntax",
        r"missing operand",
        r"missing expression",
        r"incomplete input",
        r"near \"",
        r"near '",
    ]

    SCHEMA_PATTERNS = [
        r"no such table",
        r"no such column",
        r"no such function",
        r"unknown column",
        r"unknown table",
        r"relation .* does not exist",
        r"table .* does not exist",
        r"column .* does not exist",
        r"does not exist",
        r"doesn't exist",
        r"invalid identifier",
        r"unresolved",
        r"ambiguous column",
        r"not found",
    ]

    def solve(self, question: str) -> str:
        sql = self._generate_initial_sql(question)
        result = self._execute(sql) if sql.strip() else {"ok": False, "rows": [], "error": "No SQL was extracted"}

        if result.get("ok"):
            return sql

        for _ in range(2):
            error = result.get("error") or "Unknown execution error"
            category = self._classify_error(error, sql)
            prompt = self._build_repair_prompt(question, sql, error, category)
            sql = self._generate_sql(prompt)

            if not sql.strip():
                result = {"ok": False, "rows": [], "error": "No SQL was extracted from repair response"}
                continue

            result = self._execute(sql)
            if result.get("ok"):
                return sql

        return sql

    def _generate_initial_sql(self, question: str) -> str:
        prompt = (
            "You are a SQL expert. Given the database schema below, write a single SQL query that answers the question.\n\n"
            f"### Database Schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            "Return only the SQL query, without any explanation or markdown formatting."
        )
        return self._generate_sql(prompt)

    def _generate_sql(self, prompt: str) -> str:
        response = self.llm(prompt, system="", temperature=0.0, n=1)
        text = self._response_to_text(response)
        sql = bridge.extract_sql(text or "")
        return (sql or "").strip()

    @classmethod
    def _response_to_text(cls, response) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, (list, tuple)):
            if not response:
                return ""
            return cls._response_to_text(response[0])
        if isinstance(response, dict):
            choices = response.get("choices")
            if isinstance(choices, (list, tuple)) and choices:
                return cls._response_to_text(choices[0])
            if response.get("content") is not None:
                return cls._response_to_text(response.get("content"))
            if response.get("text") is not None:
                return cls._response_to_text(response.get("text"))
            if response.get("message") is not None:
                return cls._response_to_text(response.get("message"))
            return ""
        if hasattr(response, "choices"):
            choices = response.choices
            if choices:
                return cls._response_to_text(choices[0])
        if hasattr(response, "message"):
            return cls._response_to_text(response.message)
        if hasattr(response, "content"):
            return cls._response_to_text(response.content)
        if hasattr(response, "text"):
            return cls._response_to_text(response.text)
        return str(response)

    def _execute(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "Invalid execution result"}
        return result

    @classmethod
    def _classify_error(cls, error: str, sql: str) -> str:
        if not (sql or "").strip():
            return "syntax"
        err = (error or "").lower()
        for pattern in cls.SCHEMA_PATTERNS:
            if re.search(pattern, err):
                return "schema"
        for pattern in cls.SYNTAX_PATTERNS:
            if re.search(pattern, err):
                return "syntax"
        return "semantics"

    def _build_repair_prompt(self, question: str, sql: str, error: str, category: str) -> str:
        if category == "syntax":
            instruction = (
                "The previous SQL query failed with a syntax issue. Fix the SQL syntax and return only the corrected SQL query. "
                "Do not change the intended meaning of the query."
            )
        elif category == "schema":
            instruction = (
                "The previous SQL query failed with a schema issue, such as an invalid table or column reference. "
                "Use only table and column names exactly as they appear in the schema. "
                "Check all joins, aliases, and identifiers. Return only the corrected SQL query."
            )
        else:
            instruction = (
                "The previous SQL query failed with a semantics issue: it may run but not answer the question correctly. "
                "Read the question carefully and write a corrected SQL query that uses the schema accurately. "
                "Return only the corrected SQL query."
            )

        return (
            "You are a SQL expert. A previous SQL query failed or was incorrect.\n\n"
            f"### Database Schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            f"### Previous SQL\n{sql}\n\n"
            f"### Error Message\n{error}\n\n"
            f"{instruction}"
        )