"""Decomposes a Text-to-SQL question into ordered sub-questions, generates SQL for each, and assembles the pieces into a final SQL query."""
import json
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS1Decompose(SQLHarness):
    _DECOMPOSE_SYSTEM = "You are a planner for Text-to-SQL tasks."
    _SQL_SYSTEM = "You are an expert SQL developer."
    _ASSEMBLY_SYSTEM = "You are an expert SQL developer who combines SQL fragments."

    def solve(self, question: str) -> str:
        schema = self.schema or ""

        # Step 1: Decompose the original question into ordered sub-questions.
        decomp_prompt = f"""Database schema:
{schema}

Original question:
{question}

Break the original question into an ordered JSON list of sub-questions that, when solved in order, can be used to construct the final SQL query. Return only a JSON list of strings, e.g. ["sub-question 1", "sub-question 2"]. Do not include any other text."""
        try:
            decomp_raw = self.llm(decomp_prompt, system=self._DECOMPOSE_SYSTEM, temperature=0.0, n=1)
            sub_questions = self._parse_json_list(decomp_raw)
        except Exception:
            sub_questions = []

        if not sub_questions:
            return self._direct_sql(question)

        # Step 2: Solve each sub-question with a small dedicated LLM call.
        sub_sqls = []
        context_parts = []
        for i, sq in enumerate(sub_questions):
            if context_parts:
                previous = "\n\n".join(context_parts)
                prompt = f"""Database schema:
{schema}

Previous sub-questions and their SQL queries:
{previous}

Current sub-question:
{sq}

Write a single SQL query that answers the current sub-question. You may reference previous SQL queries as CTEs or subqueries if useful. Return only the SQL query."""
            else:
                prompt = f"""Database schema:
{schema}

Sub-question:
{sq}

Write a single SQL query that answers this sub-question. Return only the SQL query."""

            try:
                raw = self.llm(prompt, system=self._SQL_SYSTEM, temperature=0.0, n=1)
                sql = self._extract_sql(raw)
            except Exception:
                sql = ""

            if sql:
                sub_sqls.append((sq, sql))
                context_parts.append(f"Sub-question {i + 1}: {sq}\nSQL:\n{sql}")

        if not sub_sqls:
            return self._direct_sql(question)

        # Step 3: Assemble the generated SQL fragments into one final SQL query.
        combined = "\n\n".join(context_parts)
        assembly_prompt = f"""Database schema:
{schema}

Original question:
{question}

Sub-queries generated from decomposed sub-questions:
{combined}

Using these SQL fragments, write a single final SQL query that answers the original question. Return only the SQL query."""

        try:
            final_raw = self.llm(assembly_prompt, system=self._ASSEMBLY_SYSTEM, temperature=0.0, n=1)
            final_sql = self._extract_sql(final_raw)
        except Exception:
            final_sql = ""

        if not final_sql:
            if len(sub_sqls) == 1:
                final_sql = sub_sqls[0][1]
            else:
                final_sql = self._direct_sql(question)

        return final_sql or ""

    def _direct_sql(self, question: str) -> str:
        """Fallback: generate SQL directly without decomposition."""
        schema = self.schema or ""
        prompt = f"""Database schema:
{schema}

Question:
{question}

Write a single SQL query that answers the question. Return only the SQL query."""
        raw = self.llm(prompt, system=self._SQL_SYSTEM, temperature=0.0, n=1)
        return self._extract_sql(raw)

    @staticmethod
    def _parse_json_list(text: str):
        """Parse a JSON list of strings or fall back to line-by-line parsing."""
        if not text:
            return []

        # Try to extract JSON list.
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
                if isinstance(data, list):
                    result = []
                    for item in data:
                        if isinstance(item, str):
                            s = item.strip()
                            if s:
                                result.append(s)
                    if result:
                        return result
            except Exception:
                pass

        lines = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("