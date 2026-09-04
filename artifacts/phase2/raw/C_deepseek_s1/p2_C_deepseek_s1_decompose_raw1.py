"""Decompose a natural-language question into ordered sub-questions, generate SQL for each, and assemble the final SQL query."""
import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS1Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: break into ordered sub-questions
        try:
            sub_questions = self._decompose(question)
        except Exception:
            sub_questions = []

        if not sub_questions:
            return self._direct_sql(question)

        # Step 2: answer each sub-question with a small SQL generation call
        pairs = []
        for idx, sub in enumerate(sub_questions, 1):
            try:
                sub_sql = self._answer_subquestion(sub, idx, len(sub_questions))
                sub_sql = bridge.extract_sql(sub_sql) or ""
                if sub_sql:
                    pairs.append((sub, sub_sql))
            except Exception:
                continue

        if not pairs:
            return self._direct_sql(question)

        # Step 3: assemble the final SQL
        try:
            final_sql = self._assemble(question, pairs)
            final_sql = bridge.extract_sql(final_sql) or ""
        except Exception:
            final_sql = ""

        if not final_sql:
            if len(pairs) == 1:
                return pairs[0][1]
            return self._direct_sql(question)

        return final_sql

    def _decompose(self, question: str):
        schema = self.schema or ""
        prompt = f"""You are an expert SQL planner. Given a database schema and a user question, break the question into an ordered list of smaller, self-contained sub-questions. Each sub-question must be answerable by one SQL SELECT query.

Output ONLY a JSON array of strings.

Schema:
{schema}

Question:
{question}

Return the JSON array now."""
        resp = self._call_llm(prompt, system="You are a helpful SQL decomposition assistant.")
        return self._extract_json_list(resp)

    def _answer_subquestion(self, sub: str, idx: int, total: int) -> str:
        schema = self.schema or ""
        prompt = f"""You are an expert SQLite SQL developer. Write a single SQL SELECT query that answers the sub-question. Use only the schema below. Return only the SQL query, no explanations or markdown.

Schema:
{schema}

Sub-question ({idx}/{total}):
{sub}

SQL:"""
        return self._call_llm(prompt, system="You are a helpful SQL coding assistant.")

    def _assemble(self, question: str, pairs) -> str:
        schema = self.schema or ""
        parts = []
        for i, (sub, sql) in enumerate(pairs, 1):
            parts.append(f"{i}. Sub-question: {sub}\nSQL:\n{sql}")
        parts_text = "\n\n".join(parts)

        prompt = f"""You are an expert SQLite SQL developer. Use the ordered sub-questions and their SQL queries below to write a final single SQL SELECT query that answers the original question. You may combine the SQL fragments using subqueries, CTEs, JOINs, or UNION as appropriate. Return only the final SQL query.

Schema:
{schema}

Original question:
{question}

Sub-queries:
{parts_text}

Final SQL:"""
        return self._call_llm(prompt, system="You are a helpful SQL coding assistant.")

    def _direct_sql(self, question: str) -> str:
        schema = self.schema or ""
        prompt = f"""Schema:
{schema}

Question:
{question}

Write a SQL SELECT query that answers the question. Return only the SQL query."""
        resp = self._call_llm(prompt, system="You are a helpful SQL coding assistant.")
        return bridge.extract_sql(resp) or ""

    def _call_llm(self, prompt: str, system: str = "") -> str:
        try:
            resp = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        if isinstance(resp, str):
            return resp
        if resp is None:
            return ""
        if isinstance(resp, list):
            return str(resp[0]) if resp else ""
        if isinstance(resp, dict):
            for key in ("text", "content", "completion", "message", "output"):
                if key in resp:
                    return str(resp[key])
            return str(resp)

        for attr in ("text", "content", "completion", "message"):
            if hasattr(resp, attr):
                val = getattr(resp, attr)
                if val is not None:
                    return str(val)
        return str(resp)

    def _extract_json_list(self, text: str):
        text = text.strip()
        # Remove Markdown code fences
        text = re.sub(r"