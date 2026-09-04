"""Classifies SQL execution failures as syntax, schema, or semantics and applies a class-specific fix prompt for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS1ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema
        current_sql = self._generate_sql(question, schema)
        if not current_sql:
            current_sql = "SELECT 1"

        for _ in range(2):
            result = self.execute(current_sql)
            if result.get("ok"):
                return current_sql

            error = result.get("error") or "Unknown execution error"
            category = self._classify_error(error)
            fixed_sql = self._fix_for_category(question, schema, current_sql, error, category)
            if fixed_sql:
                current_sql = fixed_sql

        return current_sql

    def _generate_sql(self, question: str, schema: str) -> str:
        prompt = (
            "Given the following database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a SQL query to answer the question. Output only the SQL query."
        )
        raw = self._call_llm(prompt, system="You are a SQL expert.")
        sql = bridge.extract_sql(raw)
        if sql and sql.strip():
            return sql.strip()
        return (raw or "").strip()

    def _classify_error(self, error: str) -> str:
        e = error.lower()

        syntax_markers = [
            "syntax",
            "parse",
            "near",
            "unexpected",
            "expected",
            "mismatched",
            "token recognition",
            "extraneous input",
            "could not execute",
            "sqlite syntax",
            "sqlite3.syntaxerror",
            "sqlite3.operationalerror",
        ]
        schema_markers = [
            "no such table",
            "no such column",
            "unknown table",
            "unknown column",
            "does not exist",
            "not exist",
            "no table",
            "no column",
            "ambiguous",
            "unresolved",
            "cannot find",
            "missing table",
            "missing column",
            "undefined table",
            "undefined column",
            "invalid reference",
            "cannot reference",
            "relation",
            "attribute",
        ]

        for marker in syntax_markers:
            if marker in e:
                return "syntax"
        for marker in schema_markers:
            if marker in e:
                return "schema"
        return "semantics"

    def _fix_for_category(
        self,
        question: str,
        schema: str,
        current_sql: str,
        error: str,
        category: str,
    ) -> str:
        system = "You are a SQL expert. Output only the corrected SQL query."

        if category == "syntax":
            prompt = (
                "A SQL query has a syntax error.\n\n"
                f"SQL:\n{current_sql}\n\n"
                f"Error:\n{error}\n\n"
                "Fix the syntax error and output only the corrected SQL query. "
                "Preserve the original meaning and do not change table/column names."
            )
        elif category == "schema":
            prompt = (
                "A SQL query references tables or columns that do not exist in the database schema.\n\n"
                f"SQL:\n{current_sql}\n\n"
                f"Error:\n{error}\n\n"
                f"Schema:\n{schema}\n\n"
                f"Question:\n{question}\n\n"
                "Rewrite the SQL using only valid tables and columns from the schema, "
                "while preserving the question's intent. Output only SQL."
            )
        else:
            prompt = (
                "A SQL query fails for a semantic reason that is not a syntax error "
                "and not a missing table/column error.\n\n"
                f"SQL:\n{current_sql}\n\n"
                f"Error:\n{error}\n\n"
                f"Schema:\n{schema}\n\n"
                f"Question:\n{question}\n\n"
                "Analyze the schema and question carefully, then write a corrected SQL query "
                "that accurately answers the question. Output only SQL."
            )

        raw = self._call_llm(prompt, system=system)
        fixed = bridge.extract_sql(raw)
        if fixed and fixed.strip():
            return fixed.strip()
        return (raw or "").strip()

    def _call_llm(self, prompt: str, system: str = "") -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)

        if isinstance(response, str):
            return response

        if isinstance(response, dict):
            choices = response.get("choices") or []
            if choices:
                choice = choices[0]
                if isinstance(choice, dict):
                    message = choice.get("message") or {}
                    if isinstance(message, dict):
                        return message.get("content") or ""
                    return choice.get("text") or ""
        elif hasattr(response, "choices"):
            choices = response.choices
            if choices:
                choice = choices[0]
                if hasattr(choice, "message") and hasattr(choice.message, "content"):
                    return choice.message.content or ""
                if hasattr(choice, "text"):
                    return choice.text or ""

        return str(response or "")