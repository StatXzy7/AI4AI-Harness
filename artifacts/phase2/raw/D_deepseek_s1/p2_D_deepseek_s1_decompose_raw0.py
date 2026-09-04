"""Break a natural-language question into ordered sub-questions, answer each with a focused Text-to-SQL call, and assemble the final SQL."""
import json
import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS1Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema

        # Stage 1: decompose the question into ordered sub-questions.
        decomposition_prompt = self._build_decomposition_prompt(question, schema)
        decomposition_raw = self.llm(
            decomposition_prompt,
            system="You decompose Text-to-SQL questions into clear ordered sub-questions.",
            temperature=0.0,
            n=1,
        )
        sub_questions = self._parse_sub_questions(decomposition_raw)
        if not sub_questions:
            sub_questions = [question]

        # Stage 2: answer each sub-question with a focused SQL generation call.
        sub_sqls = []
        for i, sub_question in enumerate(sub_questions, 1):
            sub_prompt = self._build_sub_sql_prompt(sub_question, schema, i, len(sub_questions))
            sub_raw = self.llm(
                sub_prompt,
                system="You write a single SQL query for a sub-question.",
                temperature=0.0,
                n=1,
            )
            sub_sql = bridge.extract_sql(sub_raw)
            if not sub_sql:
                # Fallback: ask LLM again with stronger formatting instruction.
                sub_prompt_fallback = (
                    sub_prompt
                    + "\n\nReturn only the SQL query, no explanation, no code fences."
                )
                sub_raw = self.llm(
                    sub_prompt_fallback,
                    system="You write a single SQL query for a sub-question.",
                    temperature=0.0,
                    n=1,
                )
                sub_sql = bridge.extract_sql(sub_raw)
            sub_sqls.append((sub_question, sub_sql))

        # Stage 3: assemble the final SQL from the sub-question SQLs.
        assembly_prompt = self._build_assembly_prompt(question, schema, sub_sqls)
        final_raw = self.llm(
            assembly_prompt,
            system="You assemble a final SQL query from sub-queries.",
            temperature=0.0,
            n=1,
        )
        final_sql = bridge.extract_sql(final_raw)
        if not final_sql:
            # Last-resort fallback: use the first non-empty sub-SQL.
            for _, sql in sub_sqls:
                if sql:
                    final_sql = sql
                    break
        return final_sql

    def _build_decomposition_prompt(self, question: str, schema: str) -> str:
        return (
            "You are given a database schema and a natural-language question.\n"
            "Break the question into an ordered list of smaller sub-questions that must be solved "
            "sequentially to produce the final SQL answer.\n"
            "Each sub-question must be self-contained and answerable by a single SQL query on the schema.\n"
            "Return ONLY a JSON list of strings. Example: [\"Find ...\", \"Then ...\"]\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "JSON list of ordered sub-questions:"
        )

    def _build_sub_sql_prompt(self, sub_question: str, schema: str, idx: int, total: int) -> str:
        return (
            f"Database schema:\n{schema}\n\n"
            f"Sub-question {idx}/{total}:\n{sub_question}\n\n"
            "Write a single SQL query that answers this sub-question. "
            "Return only SQL, no explanation, no markdown fences."
        )

    def _build_assembly_prompt(self, question: str, schema: str, sub_sqls: list) -> str:
        lines = []
        for i, (sub_q, sub_sql) in enumerate(sub_sqls, 1):
            lines.append(f"{i}. Sub-question: {sub_q}\n   SQL: {sub_sql if sub_sql else '(empty)'}")
        sub_block = "\n".join(lines)
        return (
            f"Database schema:\n{schema}\n\n"
            f"Original question:\n{question}\n\n"
            "The following ordered sub-queries were produced for this question:\n"
            f"{sub_block}\n\n"
            "Combine these sub-queries into one final SQL query that correctly answers the original question. "
            "Return only the final SQL, no explanation, no markdown fences."
        )

    def _parse_sub_questions(self, text: str):
        if not text:
            return []
        cleaned = text.strip()
        if cleaned.startswith("