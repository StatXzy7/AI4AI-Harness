"""Decompose the question into ordered sub-questions, answer each with small LLM calls, and assemble the final SQL."""

import ast
import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS1Decompose(SQLHarness):
    """Decompose, answer, and assemble SQL in separate controlled steps."""

    MAX_SUBQUESTIONS = 5
    MAX_REPAIRS = 2
    MAX_CONTEXT_CHARS = 12000

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        schema = self._trim(getattr(self, "schema", "") or "")

        sub_questions = self._decompose(question, schema) if question else []
        if not sub_questions:
            sub_questions = [question] if question else ["Return a trivial valid query."]

        sub_answers = []
        for idx, sub_question in enumerate(sub_questions[: self.MAX_SUBQUESTIONS], 1):
            sub_answers.append(
                self._answer_sub_question(idx, sub_question, question, schema)
            )

        context = self._format_context(sub_answers)

        final_sql = self._assemble(question, schema, context)
        final_sql, final_ok = self._repair_loop(final_sql, question, schema, context)
        if final_ok and final_sql:
            return final_sql

        fallback_sql = self._fallback_direct(question, schema, context)
        fallback_sql, fallback_ok = self._repair_loop(
            fallback_sql,
            question,
            schema,
            context,
        )
        if fallback_ok and fallback_sql:
            return fallback_sql

        return final_sql or fallback_sql or "SELECT 1"

    def _decompose(self, question, schema):
        system = "You are a precise SQL planning assistant. Output only valid JSON."
        prompt = (
            "Break the user's question into ordered sub-questions for building one SQL query.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only a JSON array of 1 to 5 strings. Each string is one sub-question. "
            "Do not answer the sub-questions. Do not output SQL, markdown, or explanation.\n"
            'Example output: ["Which tables are relevant?", "What filters apply?", "What aggregation is needed?"]'
        )

        raw = self._call_llm(prompt, system)
        items = self._parse_json_list(raw)
        if not items:
            items = self._lines_from_text(raw)

        cleaned = []
        for item in items:
            text = self._normalize_subquestion(item)
            if text and text not in cleaned:
                cleaned.append(text)

        return cleaned[: self.MAX_SUBQUESTIONS]

    def _answer_sub_question(self, idx, sub_question, question, schema):
        system = "You are a concise SQL analyst. Output only valid JSON."
        prompt = (
            "Answer only the given sub-question while preparing a SQL query.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Main question:\n{question}\n\n"
            f"Sub-question {idx}:\n{sub_question}\n\n"
            "Return only a JSON object with keys: answer, tables, columns, conditions, sql_fragment.\n"
            "- answer: concise answer or decision.\n"
            "- tables: array of relevant table names.\n"
            "- columns: array of relevant column names.\n"
            "- conditions: array of SQL conditions or filters.\n"
            "- sql_fragment: optional small SQL expression, or empty string.\n"
            "Do not output markdown or explanation."
        )

        raw = self._call_llm(prompt, system)
        raw_text = self._as_text(raw)
        obj = self._parse_json_object(raw_text) or {}

        answer = str(obj.get("answer", "")).strip()
        if not answer:
            if raw_text.strip().startswith(("{", "[")):
                answer = "No answer."
            else:
                answer = self._first_sentence(raw_text) or "No answer."

        sql_fragment = ""
        if obj:
            sql_fragment = self._extract_sql(str(obj.get("sql_fragment", "")))
        if not sql_fragment and not obj:
            sql_fragment = self._extract_sql(raw_text)
        if not sql_fragment and "