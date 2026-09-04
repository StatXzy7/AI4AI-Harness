"""Generate SQL, execute it, classify failures as syntax/schema/semantics, and prompt for targeted fixes for up to two rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2ErrorClassify(SQLHarness):
    """A harness that repairs Text-to-SQL errors with error-class-specific LLM prompts."""

    def solve(self, question: str) -> str:
        sql = self._generate_initial(question)

        for _ in range(2):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = str(result.get("error") or "")
            category = self._classify_error(error)
            sql = self._generate_fix(question, sql, error, category)

        return sql

    def _generate_initial(self, question: str) -> str:
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. "
            "Output only the SQL query, no explanation."
        )
        return self._call_and_extract(prompt, system="You are a SQL expert.")

    def _generate_fix(self, question: str, bad_sql: str, error: str, category: str) -> str:
        instructions = {
            "syntax": (
                "Fix the SQL syntax while preserving the intended query. "
                "Ensure correct quoting, parentheses, joins, aliases, and punctuation. "
                "Output only the corrected SQL query, no explanation."
            ),
            "schema": (
                "Rewrite the SQL so every table and column identifier exactly matches the database schema. "
                "Replace any missing identifier with the closest available schema column/table, "
                "or restructure the query to use only schema objects. "
                "Output only the corrected SQL query, no explanation."
            ),
            "semantics": (
                "Rewrite the SQL to remove the semantic/execution error. "
                "Adjust data types, aggregate functions, GROUP BY, HAVING, "
                "subquery cardinality, or function names/arguments as needed. "
                "Preserve the original question intent. "
                "Output only the corrected SQL query, no explanation."
            ),
        }
        instruction = instructions.get(category, instructions["semantics"])

        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Original SQL query:\n{bad_sql}\n\n"
            f"Execution error:\n{error}\n\n"
            f"Error class: {category}\n"
            f"Fix instruction: {instruction}\n"
        )
        return self._call_and_extract(prompt, system="You are a SQL repair expert.")

    def _call_and_extract(self, prompt: str, system: str = "") -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""

        text = str(response)
        sql = bridge.extract_sql(text)

        if isinstance(sql, (list, tuple)):
            sql = sql[0] if sql else ""
        if sql and isinstance(sql, str):
            return sql.strip()

        raw = text.strip()
        if raw:
            return raw
        return "SELECT 1;"

    def _classify_error(self, error: str) -> str:
        e = error.lower()

        syntax_markers = (
            "syntax error",
            "parse error",
            "syntaxerror",
            "unexpected",
            "near ",
            "incorrect syntax",
            "incomplete input",
            "unrecognized token",
            "unclosed",
            "quotation",
            "syntax",
        )

        schema_markers = (
            "no such table",
            "no such column",
            "unknown table",
            "unknown column",
            "does not exist",
            "not found",
            "ambiguous column",
            "unresolved",
            "invalid identifier",
            "missing from",
            "unknown identifier",
            "could not resolve",
            "has no column",
            "cannot find column",
            "cannot find table",
        )

        semantics_markers = (
            "no such function",
            "misuse of aggregate",
            "group by",
            "having",
            "type mismatch",
            "datatype",
            "division by zero",
            "constraint",
            "foreign key",
            "unique constraint",
            "cannot",
            "order by",
            "limit",
            "offset",
            "inconsistent",
            "subquery returns more than one row",
            "sub-select returns",
            "expected",
            "wrong number of arguments",
            "aggregate",
        )

        if any(marker in e for marker in syntax_markers):
            return "syntax"
        if any(marker in e for marker in schema_markers):
            return "schema"
        if any(marker in e for marker in semantics_markers):
            return "semantics"

        return "semantics"