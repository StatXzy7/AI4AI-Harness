"""A harness that decomposes a Text-to-SQL question into ordered sub-questions, answers each with a small LLM call, and assembles the final SQL."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema or ""

        # 1. Decompose the original question into ordered sub-questions.
        subquestions = self._decompose(question, schema)
        if not subquestions:
            subquestions = [question]

        # 2. Answer each sub-question with a small LLM call and execute it.
        results: List[Dict[str, Any]] = []
        for sub_q in subquestions:
            sql = self._generate_subquery_sql(question, schema, sub_q, results)
            execution = self._execute_sql(sql)
            results.append({
                "sub_question": sub_q,
                "sql": sql,
                **execution,
            })

        # 3. Assemble the final SQL from the sub-question/answer context.
        return self._assemble_final_sql(question, schema, results)

    def _llm_text(self, prompt: str, system: str = "") -> str:
        """Call the LLM with n=1 and coerce whatever it returns into text."""
        response = self.llm(prompt, system=system, temperature=0.0, n=1)

        if isinstance(response, list):
            if not response:
                return ""
            first = response[0]
            if isinstance(first, dict):
                return str(first.get("text", first.get("content", first)))
            return str(first)

        if isinstance(response, dict):
            return str(response.get("text", response.get("content", response)))

        return str(response)

    def _decompose(self, question: str, schema: str) -> List[str]:
        system = "You are an expert data analyst who plans SQL queries."
        prompt = (
            "You are given a SQLite database schema.\n\n"
            f"Schema:\n{schema or 'No schema provided'}\n\n"
            f"Question:\n{question}\n\n"
            "Break the question into 2-5 ordered, concise sub-questions that can each be answered with a SQL query. "
            'Return ONLY a JSON list of strings, for example: ["Find ...", "Then ..."]. '
            "Do not include any explanation or markdown."
        )

        response = self._llm_text(prompt, system=system)
        subquestions = self._parse_subquestions(response)

        if not subquestions:
            return [question]

        return subquestions[:5]

    def _parse_subquestions(self, text: str) -> List[str]:
        cleaned = text.strip()
        if not cleaned:
            return []

        # Remove triple backticks and optional "json" marker.
        cleaned = re.sub(r"