"""Two-stage Text-to-SQL: first extract relevant schema snippets, then generate SQL grounded in those snippets."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AMinimaxS1G7(SQLHarness):
    def _extract_schema_keywords(self, question: str) -> str:
        """Stage 1: ask the LLM to identify which tables/columns from the schema are relevant."""
        prompt = (
            "You are a database schema analyst. Given a natural language question and a database "
            "schema, your job is to extract ONLY the schema elements (tables and columns) that are "
            "necessary to answer the question.\n\n"
            "RULES:\n"
            "1. Output a concise list of relevant CREATE TABLE / column definitions.\n"
            "2. Include foreign-key relationships when two tables must be joined.\n"
            "3. Do NOT invent columns that are not in the provided schema.\n"
            "4. Be minimal but complete: a downstream SQL generator will see ONLY your output.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION: {question}\n\n"
            "RELEVANT SCHEMA SNIPPET:"
        )
        return self.llm(prompt, system="You are a precise schema analyst.", temperature=0.0, n=1)

    def _generate_sql(self, question: str, schema_snippet: str) -> str:
        """Stage 2: generate SQL conditioned on the focused schema snippet."""
        prompt = (
            "You are an expert SQL generator. Write a single SQLite-compatible SQL query that "
            "answers the user's question using ONLY the schema snippet provided below.\n\n"
            f"SCHEMA SNIPPET:\n{schema_snippet}\n\n"
            f"QUESTION: {question}\n\n"
            "Output ONLY the SQL query, no prose, no markdown fences."
        )
        raw = self.llm(prompt, system="You write precise SQL.", temperature=0.0, n=1)
        return bridge.extract_sql(raw)

    def solve(self, question: str) -> str:
        # Stage 1: shrink the schema to what is plausibly relevant.
        schema_snippet = self._extract_schema_keywords(question)

        # Stage 2: generate SQL conditioned on the trimmed schema.
        sql = self._generate_sql(question, schema_snippet)

        # Light verification: if it parses + executes without error, keep it.
        # If it fails, retry once with the original full schema as a fallback.
        result = self.execute(sql)
        if result.get("ok"):
            return sql

        # Fallback regeneration with the full schema.
        fallback_prompt = (
            "You are an expert SQL generator. Write a single SQLite-compatible SQL query that "
            "answers the user's question using the provided schema.\n\n"
            f"SCHEMA:\n{self.schema}\n\n"
            f"QUESTION: {question}\n\n"
            f"Previous attempt failed with error: {result.get('error', '')}\n\n"
            "Output ONLY the SQL query, no prose, no markdown fences."
        )
        raw = self.llm(fallback_prompt, system="You write precise SQL.", temperature=0.0, n=1)
        sql2 = bridge.extract_sql(raw)
        check = self.execute(sql2)
        if check.get("ok"):
            return sql2
        return sql2  # return best-effort even if it still fails