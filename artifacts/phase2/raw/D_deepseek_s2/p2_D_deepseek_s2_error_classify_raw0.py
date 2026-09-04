"""Generate SQL, execute it, classify failures as syntax/schema/semantics, and apply a targeted fix for up to two rounds."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        current_sql = self._generate_initial_sql(question)

        for _ in range(2):  # up to two repair rounds
            result = self.execute(current_sql)
            if result.get("ok"):
                return current_sql

            error = result.get("error", "")
            category = self._classify_error(question, current_sql, error)

            if category == "syntax":
                current_sql = self._fix_syntax(question, current_sql, error)
            elif category == "schema":
                current_sql = self._fix_schema(question, current_sql, error)
            else:
                current_sql = self._fix_semantics(question, current_sql, error)

            current_sql = bridge.extract_sql(current_sql)

        return current_sql

    def _call_llm(self, prompt: str, system: str = "") -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, (list, tuple)):
            return str(response[0]) if response else ""
        return str(response)

    def _generate_initial_sql(self, question: str) -> str:
        prompt = f"""Given the following database schema:
{self.schema}

Question:
{question}

Write a single SQL query that answers the question.
Return only the SQL query, without markdown fences or explanation."""
        response = self._call_llm(prompt, system="You are an expert SQL generator.")
        return bridge.extract_sql(response)

    def _classify_error(self, question: str, sql: str, error: str) -> str:
        prompt = f"""Schema:
{self.schema}

Question:
{question}

Generated SQL:
{sql}

Execution error:
{error}

Classify this failure into exactly one category:
- syntax: malformed SQL or parse error
- schema: nonexistent or incorrectly named tables/columns
- semantics: SQL syntax and schema are valid, but the logic is wrong or does not answer the question

Return only one word: syntax, schema, or semantics."""
        response = self._call_llm(prompt)
        category = self._parse_category(response)
        if category:
            return category
        return self._heuristic_classify(error)

    def _parse_category(self, response: str) -> str:
        text = response.strip().lower()
        if text == "syntax":
            return "syntax"
        if text == "schema":
            return "schema"
        if text in {"semantics", "semantic"}:
            return "semantics"

        # Fallback substring checks, preferring explicit category words.
        if "semantics" in text:
            return "semantics"
        if "schema" in text:
            return "schema"
        if "syntax" in text:
            return "syntax"
        return ""

    def _heuristic_classify(self, error: str) -> str:
        e = error.lower()
        syntax_markers = [
            "syntax", "parse", "near", "unexpected", "missing expression",
            "ora-", "syntax error", "malformed"
        ]
        schema_markers = [
            "no such table", "no such column", "unknown column", "relation",
            "does not exist", "invalid identifier", "ambiguous column",
            "cannot find", "not a valid table", "not a valid column"
        ]
        if any(m in e for m in syntax_markers):
            return "syntax"
        if any(m in e for m in schema_markers):
            return "schema"
        return "semantics"

    def _fix_syntax(self, question: str, sql: str, error: str) -> str:
        prompt = f"""Schema:
{self.schema}

Question:
{question}

The following SQL had a syntax error:
{sql}

Error:
{error}

Fix only the syntax error while preserving the intended logic.
Return only the corrected SQL query, without markdown fences or explanation."""
        response = self._call_llm(prompt)
        return bridge.extract_sql(response)

    def _fix_schema(self, question: str, sql: str, error: str) -> str:
        prompt = f"""Schema:
{self.schema}

Question:
{question}

The following SQL used incorrectly named tables or columns:
{sql}

Error:
{error}

Rewrite the SQL using only tables and columns that exist in the schema.
Return only the corrected SQL query, without markdown fences or explanation."""
        response = self._call_llm(prompt)
        return bridge.extract_sql(response)

    def _fix_semantics(self, question: str, sql: str, error: str) -> str:
        prompt = f"""Schema:
{self.schema}

Question:
{question}

The following SQL is syntactically valid and uses existing schema objects, but its logic may be wrong:
{sql}

Execution error or context:
{error}

Analyze the question carefully and rewrite the SQL to answer it correctly.
Return only the corrected SQL query, without markdown fences or explanation."""
        response = self._call_llm(prompt)
        return bridge.extract_sql(response)