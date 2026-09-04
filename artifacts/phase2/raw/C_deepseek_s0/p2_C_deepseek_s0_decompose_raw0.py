"""Decomposes a complex Text-to-SQL question into ordered sub-questions, solves each with a small LLM call, and assembles the final SQL query."""

import json
import re
from typing import List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS0Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        subquestions = self._decompose(question)
        if not subquestions:
            subquestions = [question]

        sub_sqls = []
        for subq in subquestions:
            prompt = self._subquestion_prompt(subq)
            raw = self._call_llm(prompt, system="You are a SQL expert. Return only SQL.")
            sql = bridge.extract_sql(raw)
            if not sql:
                fallback_prompt = (
                    f"Database schema:\n{self.schema}\n\n"
                    f"Write a SQL query for: {subq}\n"
                    "Return only SQL."
                )
                raw = self._call_llm(fallback_prompt, system="You are a SQL expert. Return only SQL.")
                sql = bridge.extract_sql(raw)
            sub_sqls.append(sql)

        usable_sqls = [s for s in sub_sqls if s]
        if not usable_sqls:
            raw = self._call_llm(
                f"Database schema:\n{self.schema}\n\nQuestion: {question}\nWrite a SQL query. Return only SQL.",
                system="You are a SQL expert. Return only SQL.",
            )
            return bridge.extract_sql(raw)

        assemble_prompt = self._assemble_prompt(question, subquestions, sub_sqls)
        raw_final = self._call_llm(assemble_prompt, system="You are a SQL expert. Return only SQL.")
        final_sql = bridge.extract_sql(raw_final)

        if not final_sql:
            final_sql = usable_sqls[-1]

        final_sql = self._repair_if_needed(question, final_sql)
        return final_sql

    def _call_llm(self, prompt: str, system: str = "") -> str:
        output = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(output, list):
            return output[0] if output else ""
        return output or ""

    def _decompose(self, question: str) -> List[str]:
        prompt = (
            "You are given a database schema and a user question.\n"
            "Break the question into an ordered list of simple sub-questions that can each be answered "
            "by a single SQL query over the schema.\n"
            "Return ONLY a JSON list of strings, for example: [\"Find ...\", \"Then find ...\"].\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"User question:\n{question}\n"
        )
        raw = self._call_llm(prompt, system="You are a helpful assistant that returns only valid JSON.")
        parsed = self._parse_json_list(raw)
        if parsed:
            return parsed

        numbered = re.findall(r"(?m)^\s*(?:\d+[\.\)]|[-*])\s+(.+)$", raw)
        if numbered:
            return [line.strip() for line in numbered]
        return [question]

    def _parse_json_list(self, raw: str) -> List[str]:
        text = raw.strip()
        text = re.sub(r"