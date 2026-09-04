"""Break a Text-to-SQL question into ordered sub-questions, solve each with a small LLM call, and assemble the final SQL."""

from __future__ import annotations

import json
from typing import Any, List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        sub_questions = self._decompose(question)
        sub_questions = self._order_subquestions(sub_questions)

        if not sub_questions:
            sub_questions = [{"step": 1, "question": question, "hint": ""}]

        fragments: List[str] = []
        previous: List[str] = []

        for idx, sq in enumerate(sub_questions, start=1):
            if isinstance(sq, str):
                sq = {"question": sq, "hint": ""}
            if not isinstance(sq, dict):
                continue

            sub_q = sq.get("question") or sq.get("text") or question
            hint = sq.get("hint") or sq.get("sql_hint") or ""
            sql = self._solve_subquestion(question, sub_q, hint, previous)

            if sql:
                fragments.append(sql)
                previous.append(sql)

        if not fragments:
            return self._single_shot(question)

        final_sql = self._assemble(question, fragments)
        if not final_sql:
            return self._single_shot(question)

        result = self.execute(final_sql)
        if result.get("ok"):
            return final_sql

        repaired = self._repair(question, final_sql, result.get("error"))
        if repaired:
            return repaired

        return final_sql

    def _decompose(self, question: str) -> List[Any]:
        prompt = f"""You are an expert SQL analyst. Given a database schema and a complex user question, break the question into 3-6 ordered sub-questions. Each sub-question must be answerable by a single SQL SELECT over the schema or over previously computed sub-questions (refer to previous CTEs as step_1, step_2, etc. if needed).

Schema:
{self.schema}

Question:
{question}

Return only a JSON array of objects with keys:
- "step": integer position starting at 1
- "question": the sub-question in plain English
- "hint": a short SQL hint for that sub-question

Example:
[{{"step": 1, "question": "Find ...", "hint": "SELECT ... FROM ..."}}]
"""
        raw = self._call_llm(prompt, system="You return only valid JSON.")
        return self._parse_json_list(raw)

    def _solve_subquestion(
        self,
        original_question: str,
        sub_question: str,
        hint: str,
        previous_fragments: List[str],
    ) -> str:
        previous_text = "None"
        if previous_fragments:
            previous_text = "\n\n".join(
                f"step_{i}:\n{f}" for i, f in enumerate(previous_fragments, start=1)
            )

        prompt = f"""Given the database schema:
{self.schema}

Previous sub-query CTEs (already computed, use these names if needed):
{previous_text}

Original question:
{original_question}

Current sub-question:
{sub_question}

SQL hint:
{hint or "None"}

Write a single SQL SELECT statement that answers the current sub-question. It may reference previous CTEs by name. Return only the SQL SELECT statement, without explanation."""
        raw = self._call_llm(prompt)
        sql = bridge.extract_sql(raw)
        if not sql:
            sql = raw.strip().strip(";")
        return sql

    def _assemble(self, question: str, fragments: List[str]) -> str:
        numbered = "\n\n".join(
            f"Sub-query {i}:\n{f}" for i, f in enumerate(fragments, start=1)
        )

        prompt = f"""Given the database schema:
{self.schema}

Original question:
{question}

Ordered sub-queries:
{numbered}

Write one final SQL SELECT statement that combines these sub-queries as CTEs named step_1, step_2, ... to answer the original question. Use the CTEs exactly as provided; do not modify their SQL. Return only the final SQL SELECT statement, without explanation."""
        raw = self._call_llm(prompt)
        sql = bridge.extract_sql(raw)
        if not sql:
            sql = raw.strip().strip(";")
        return sql

    def _single_shot(self, question: str) -> str:
        prompt = f"""Given the database schema:
{self.schema}

Question:
{question}

Write a SQL SELECT statement that answers the question. Return only the SQL SELECT statement, without explanation."""
        raw = self._call_llm(prompt)
        sql = bridge.extract_sql(raw)
        if not sql:
            sql = raw.strip().strip(";")
        return sql or ""

    def _repair(self, question: str, bad_sql: str, error: str) -> str:
        if not bad_sql:
            return ""

        prompt = f"""The following SQL query failed:
{bad_sql}

Error:
{error}

Database schema:
{self.schema}

Original question:
{question}

Return a corrected SQL SELECT statement. Return only the SQL SELECT statement, without explanation."""
        raw = self._call_llm(prompt)
        sql = bridge.extract_sql(raw)
        if not sql:
            sql = raw.strip().strip(";")
        if not sql:
            return ""

        check = self.execute(sql)
        if check.get("ok"):
            return sql
        return ""

    def _call_llm(self, prompt: str, system: str = "") -> str:
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, list):
            out = out[0] if out else ""
        return str(out)

    def _parse_json_list(self, text: str) -> List[Any]:
        text = self._strip_code_fence(text)

        try:
            data = json.loads(text)
            return self._normalize_subquestions(data)
        except Exception:
            for start_char, end_char in (("[", "]"), ("{", "}")):
                start = text.find(start_char)
                end = text.rfind(end_char)
                if start != -1 and end != -1 and end > start:
                    try:
                        data = json.loads(text[start : end + 1])
                        return self._normalize_subquestions(data)
                    except Exception:
                        continue
        return []

    def _strip_code_fence(self, text: str) -> str:
        text = text.strip()
        if text.startswith("