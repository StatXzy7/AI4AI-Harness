"""Decomposes a natural-language question into ordered sub-questions, generates a SQL fragment for each with a small LLM call, and assembles the fragments into a final CTE-based SQL query."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS0Decompose(SQLHarness):
    def solve(self, question: str) -> str:
        sub_questions = self._decompose(question)
        if not sub_questions:
            return self._direct_solve(question)

        fragments = []
        for idx, sub_q in enumerate(sub_questions, start=1):
            cte_name = f"step_{idx}"
            sql = self._solve_subquestion(question, sub_questions, idx, sub_q)
            fragments.append((cte_name, sql))

        return self._assemble(fragments)

    def _call_llm(self, prompt: str) -> str:
        out = self.llm(prompt, system="", temperature=0.0, n=1)
        if isinstance(out, list):
            return str(out[0]) if out else ""
        return str(out)

    def _decompose(self, question: str) -> list:
        prompt = f"""You are an expert SQL planner. Given a database schema and a natural-language question, decompose the question into a small ordered list of sub-questions. Each sub-question should be a single, concrete step. Later sub-questions may rely on earlier ones. The final sub-question should be equivalent to answering the original question.

Return ONLY a JSON array of strings, for example:
["Find all customers", "Find their total orders per customer"]

Do not include any explanation or code fences.

Schema:
{self.schema}

Question:
{question}
"""
        raw = self._call_llm(prompt)
        return self._parse_subquestions(raw)

    def _parse_subquestions(self, raw: str) -> list:
        if not raw:
            return []

        text = raw.strip()
        # Remove markdown code fences if present
        text = re.sub(r"