"""Executes generated SQL, classifies execution errors as syntax/schema/semantics, and applies class-specific repairs for up to two rounds."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS0ErrorClassify(SQLHarness):
    def solve(self, question: str) -> str:
        sql = self._generate_sql(question)

        for _ in range(2):
            result = self.execute(sql)
            if result.get("ok"):
                return sql

            error = result.get("error", "Unknown execution error")
            failure = self._classify_failure(question, sql, error)
            sql = self._fix_sql(question, sql, error, failure)

        return sql

    def _generate_sql(self, question: str) -> str:
        system = "You are a SQL expert. Write a single SQL query for the given question."
        prompt = f"""Database schema:
{self.schema}

Question:
{question}

Return only SQL without explanation."""
        response = self._call_llm(prompt, system)
        sql = bridge.extract_sql(response)
        return sql or response

    def _classify_failure(self, question: str, sql: str, error: str) -> str:
        system = "You are a SQL error classifier."
        prompt = f"""Database schema:
{self.schema}

Question:
{question}

Generated SQL:
{sql}

Execution error:
{error}

Classify the failure type as one of: syntax, schema, semantics.
Return only one word."""
        response = self._call_llm(prompt, system)
        lowered = response.lower()
        if "syntax" in lowered:
            return "syntax"
        if "schema" in lowered:
            return "schema"
        if "semantic" in lowered:
            return "semantics"
        return self._heuristic_classify(error)

    def _heuristic_classify(self, error: str) -> str:
        err = error.lower()
        if "syntax" in err or "parse" in err or "near" in err:
            return "syntax"
        if (
            "no such table" in err
            or "no such column" in err
            or "unknown column" in err
            or "unknown table" in err
            or "ambiguous" in err
            or "does not exist" in err
        ):
            return "schema"
        return "semantics"

    def _fix_sql(self, question: str, sql: str, error: str, failure: str) -> str:
        system = "You are a SQL expert. Fix the SQL query."
        if failure == "syntax":
            prompt = f"""Database schema:
{self.schema}

Question:
{question}

The following SQL query has a syntax error:
{sql}

Execution error:
{error}

Rewrite the SQL query to fix the syntax error while preserving the intended meaning.
Return only SQL without explanation."""
        elif failure == "schema":
            prompt = f"""Database schema:
{self.schema}

Question:
{question}

The following SQL query has a schema mismatch error:
{sql}

Execution error:
{error}

Rewrite the SQL query using the correct table and column names from the schema.
Return only SQL without explanation."""
        else:
            prompt = f"""Database schema:
{self.schema}

Question:
{question}

The following SQL query produced a semantic execution error:
{sql}

Execution error:
{error}

Rewrite the SQL query to correctly answer the question while resolving the semantic error.
Return only SQL without explanation."""
        response = self._call_llm(prompt, system)
        fixed = bridge.extract_sql(response)
        return fixed or sql

    def _call_llm(self, prompt: str, system: str = "") -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, str):
            return response.strip()
        if isinstance(response, list) and response:
            first = response[0]
            if isinstance(first, str):
                return first.strip()
            if isinstance(first, dict):
                return str(first.get("text", first.get("message", ""))).strip()
        if isinstance(response, dict):
            return str(response.get("text", response.get("message", ""))).strip()
        return str(response).strip()