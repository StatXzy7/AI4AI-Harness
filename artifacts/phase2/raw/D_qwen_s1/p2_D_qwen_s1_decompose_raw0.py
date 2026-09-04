"""Decompose the question into ordered sub-questions, answer each with small LLM calls, and assemble validated SQL."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS1Decompose(SQLHarness):
    MAX_SUBQUESTIONS = 3
    REPAIR_ATTEMPTS = 2
    SYSTEM = "You are a precise Text-to-SQL planner that outputs concise, valid SQL."

    def solve(self, question: str) -> str:
        question = str(question or "").strip()
        schema = str(getattr(self, "schema", "") or "").strip()
        if not question:
            return ""

        sub_questions = self._decompose(question, schema)
        answers = []

        for idx, sub_question in enumerate(sub_questions, 1):
            answer = self._answer_subquestion(
                question=question,
                schema=schema,
                sub_question=sub_question,
                previous_answers=answers,
                index=idx,
                total=len(sub_questions),
            )
            answers.append((sub_question, answer))

        candidates = []

        assembled = self._assemble(question, schema, answers)
        if assembled:
            candidates.append(assembled)
            if self._is_executable(assembled):
                return assembled

        error = self._execution_error(assembled) if assembled else "No SQL was produced."
        bad_sql = assembled

        for _ in range(self.REPAIR_ATTEMPTS):
            repaired = self._repair(question, schema, bad_sql, error, answers)
            if not repaired or repaired == bad_sql:
                break

            candidates.append(repaired)
            if self._is_executable(repaired):
                return repaired

            error = self._execution_error(repaired)
            bad_sql = repaired

        direct = self._direct_sql(question, schema)
        if direct:
            candidates.append(direct)
            if self._is_executable(direct):
                return direct

        return candidates[-1] if candidates else ""

    def _decompose(self, question, schema):
        prompt = (
            f"Break the following natural-language question into 2 to {self.MAX_SUBQUESTIONS} ordered sub-questions "
            "that must be answered to write the correct SQL.\n"
            "Output ONLY a JSON array of strings. No markdown, no commentary.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n"
        )
        raw = self._llm_text(prompt, system=self.SYSTEM)
        items = self._parse_string_list(raw)
        items = [item.strip() for item in items if item and item.strip()]

        if not items:
            items = self._fallback_subquestions()

        return items[: self.MAX_SUBQUESTIONS]

    def _fallback_subquestions(self):
        return [
            "Which tables and columns are required?",
            "What joins, filters, aggregations, grouping, ordering, or limits are required?",
            "What is the final SELECT statement?",
        ]

    def _answer_subquestion(self, question, schema, sub_question, previous_answers, index, total):
        if previous_answers:
            previous_text = "\n".join(
                f"{i}. {q}\n   A: {a}" for i, (q, a) in enumerate(previous_answers, 1)
            )
        else:
            previous_text = "None"

        prompt = (
            f"You are answering sub-question {index}/{total} needed to build one SQL query.\n"
            "Answer concisely. If asked for SQL parts, output only the exact SQL fragment. "
            "If asked for schema objects, output exact table/column names. "
            "Do not write a full query unless this sub-question asks for the final SELECT.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Original question:\n{question}\n\n"
            f"Previous sub-answers:\n{previous_text}\n\n"
            f"Current sub-question:\n{sub_question}\n"
        )
        answer = self._llm_text(prompt, system=self.SYSTEM)
        return self._truncate(answer, 3000)

    def _assemble(self, question, schema, answers):
        qa_text = "\n".join(
            f"{i}. {q}\n   Answer: {a}" for i, (q, a) in enumerate(answers, 1)
        )
        prompt = (
            "Using the following ordered sub-question answers, write one final SQL query.\n"
            "Return ONLY one complete SELECT statement (or WITH ... SELECT). "
            "Use exact table and column names from the schema. No explanation.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Sub-question answers:\n{qa_text}\n"
        )
        raw = self._llm_text(prompt, system=self.SYSTEM)
        return self._extract_sql(raw)

    def _repair(self, question, schema, bad_sql, error, answers):
        qa_text = "\n".join(
            f"{i}. {q}\n   Answer: {a}" for i, (q, a) in enumerate(answers, 1)
        )
        prompt = (
            "The SQL query below failed or is incorrect. Repair it so it answers the question.\n"
            "Return ONLY one complete SELECT statement (or WITH ... SELECT). No explanation.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            f"Sub-question answers:\n{qa_text}\n\n"
            f"Bad SQL:\n{bad_sql or 'None'}\n\n"
            f"Execution error:\n{error or 'Unknown error'}\n"
        )
        raw = self._llm_text(prompt, system=self.SYSTEM)
        return self._extract_sql(raw)

    def _direct_sql(self, question, schema):
        prompt = (
            "Write one SQL query that answers the question.\n"
            "Return ONLY one complete SELECT statement (or WITH ... SELECT). No explanation.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n"
        )
        raw = self._llm_text(prompt, system=self.SYSTEM)
        return self._extract_sql(raw)

    def _llm_text(self, prompt, system="", temperature=0.0, n=1):
        try:
            raw = self.llm(prompt, system=system, temperature=temperature, n=n)
        except Exception:
            return ""
        return self._coerce_text(raw)

    def _coerce_text(self, raw):
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw.strip()
        if isinstance(raw, list):
            return "\n".join(self._coerce_text(item) for item in raw).strip()
        if isinstance(raw, dict):
            for key in ("choices", "text", "content", "output", "sql", "answer", "message"):
                if key in raw:
                    return self._coerce_text(raw[key])
            return json.dumps(raw, ensure_ascii=False)
        return str(raw).strip()

    def _parse_string_list(self, text):
        text = self._coerce_text(text)
        if not text:
            return []

        text = text.replace("