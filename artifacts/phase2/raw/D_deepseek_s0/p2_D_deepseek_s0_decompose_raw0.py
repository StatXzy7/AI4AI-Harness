"""Break a Text-to-SQL question into ordered sub-questions, generate SQL for each, and assemble the final query."""

import json

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS0Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        # 1. Decompose the original question into ordered sub-questions.
        decomposition_prompt = (
            "You are given a database schema and a natural-language question.\n"
            "Break the question into an ordered list of smaller sub-questions such that each "
            "sub-question can be answered by a single SQL query over the schema.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Original question:\n{question}\n\n"
            "Return only a JSON list of strings, e.g. [\"sub-question 1\", \"sub-question 2\"]."
        )
        raw_decomposition = self.llm(
            decomposition_prompt,
            system="You are a helpful assistant that decomposes questions into sub-questions.",
            temperature=0.0,
            n=1,
        )
        sub_questions = self._parse_list(raw_decomposition)
        if not sub_questions:
            sub_questions = [question]

        # 2. Generate a SQL snippet for each sub-question independently.
        sub_sqls = []
        for sub_question in sub_questions:
            sub_prompt = (
                "You are an expert SQL writer.\n\n"
                f"Database schema:\n{schema}\n\n"
                f"Question:\n{sub_question}\n\n"
                "Write a single SQL SELECT query that answers this sub-question. "
                "Return only the SQL query, wrapped in a Markdown SQL code block."
            )
            raw_sub_sql = self.llm(
                sub_prompt,
                system="You are an expert SQL writer.",
                temperature=0.0,
                n=1,
            )
            sub_sql = bridge.extract_sql(raw_sub_sql)
            if not sub_sql:
                sub_sql = ""
            sub_sqls.append(sub_sql)

        # 3. Assemble the final SQL using the sub-question SQL snippets.
        blocks = []
        for i, (sub_question, sub_sql) in enumerate(zip(sub_questions, sub_sqls)):
            sql_text = sub_sql if sub_sql else "-- no SQL generated"
            blocks.append(f"q{i}: {sub_question}\nSQL:\n{sql_text}")
        building_blocks = "\n\n".join(blocks)

        assembly_prompt = (
            "You are an expert SQL writer.\n\n"
            f"Database schema:\n{schema}\n\n"
            f"Original question:\n{question}\n\n"
            "Below are ordered sub-questions and SQL snippets that answer them individually.\n"
            "Use these snippets as building blocks to write a single final SQL query that answers "
            "the original question. You may reference them as CTEs named q0, q1, etc.\n\n"
            f"{building_blocks}\n\n"
            "Return only the final SQL query, wrapped in a Markdown SQL code block."
        )
        raw_final_sql = self.llm(
            assembly_prompt,
            system="You are an expert SQL writer.",
            temperature=0.0,
            n=1,
        )
        final_sql = bridge.extract_sql(raw_final_sql)

        # Fallback: if assembly failed, use the last non-empty sub-query SQL.
        if not final_sql:
            for sql in reversed(sub_sqls):
                if sql:
                    final_sql = sql
                    break
        if not final_sql:
            final_sql = "SELECT 1"

        return final_sql

    def _parse_list(self, text: str):
        """Parse a JSON list of strings from LLM output, with fallback to numbered lines."""
        if not text:
            return []

        text = text.strip()
        # Remove Markdown code fences if present.
        if text.startswith("