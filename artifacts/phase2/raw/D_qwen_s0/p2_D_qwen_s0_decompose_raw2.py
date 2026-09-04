"""Decompose the question into ordered sub-questions, answer each with a small LLM call, then assemble the final SQL."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS0Decompose(SQLHarness):
    MAX_SUBQUESTIONS = 5
    MAX_ANSWER_LINES = 6

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        schema = str(getattr(self, "schema", "") or "")

        subquestions = self._decompose(question, schema)
        if not subquestions:
            subquestions = [question or "Answer the original request."]

        answers = []
        for idx, subquestion in enumerate(subquestions, start=1):
            answer = self._answer_subquestion(
                idx=idx,
                subquestion=subquestion,
                question=question,
                schema=schema,
                answers=answers,
            )
            answers.append((subquestion, answer))

        sql = self._assemble(question, schema, answers)
        if not sql:
            sql = self._fallback_direct(question, schema)

        return (sql or "").strip()

    def _llm_text(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=1)
        except TypeError:
            response = self.llm(prompt, system=system, temperature=temperature)
        return self._to_text(response)

    def _to_text(self, response) -> str:
        if response is None:
            return ""

        if isinstance(response, str):
            return response.strip()

        if isinstance(response, (list, tuple)):
            return self._to_text(response[0]) if response else ""

        if isinstance(response, dict):
            for key in ("text", "content", "output", "completion", "answer"):
                if key in response:
                    return self._to_text(response[key])
            if "choices" in response:
                return self._to_text(response["choices"])
            if "message" in response:
                return self._to_text(response["message"])

        if hasattr(response, "choices"):
            return self._to_text(response.choices)
        if hasattr(response, "text"):
            return self._to_text(response.text)
        if hasattr(response, "content"):
            return self._to_text(response.content)

        return str(response).strip()

    def _decompose(self, question: str, schema: str):
        system = (
            "You are a SQL planning assistant. Break a request into a minimal ordered list "
            "of SQL-relevant sub-questions. Output only one sub-question per line."
        )
        prompt = (
            "Schema:\n"
            f"{schema}\n\n"
            "Original question:\n"
            f"{question}\n\n"
            f"Break this into at most {self.MAX_SUBQUESTIONS} ordered sub-questions needed to write the SQL.\n"
            "Each line must be a short SQL-relevant sub-question.\n"
            "Do not include answers, numbering, bullets, markdown, or explanations."
        )
        raw = self._llm_text(prompt, system=system)
        lines = self._clean_lines(raw)
        return lines[: self.MAX_SUBQUESTIONS]

    def _answer_subquestion(self, idx: int, subquestion: str, question: str, schema: str, answers):
        system = (
            "You answer exactly one small SQL-planning sub-question. Output only the concise answer. "
            "Prefer exact table names, column names, filter values, joins, grouping, and ordering."
        )
        prompt = (
            "Schema:\n"
            f"{schema}\n\n"
            "Original question:\n"
            f"{question}\n\n"
            "Completed sub-questions:\n"
            f"{self._format_checklist(answers)}\n\n"
            f"Current sub-question {idx}:\n"
            f"{subquestion}\n\n"
            "Answer only the current sub-question with concise SQL-relevant facts.\n"
            "Do not write a full SQL query unless the sub-question explicitly asks for the final query."
        )
        raw = self._llm_text(prompt, system=system)

        lines = [line.strip() for line in str(raw or "").splitlines() if line.strip()]
        if not lines:
            return "No answer."

        if len(lines) > self.MAX_ANSWER_LINES:
            lines = lines[: self.MAX_ANSWER_LINES]

        return "\n".join(lines)

    def _assemble(self, question: str, schema: str, answers):
        system = "You are a SQL writer. Output only one complete executable SQL query."
        prompt = (
            "Schema:\n"
            f"{schema}\n\n"
            "Original question:\n"
            f"{question}\n\n"
            "Sub-question checklist:\n"
            f"{self._format_checklist(answers)}\n\n"
            "Using the checklist, write one executable SQL query that answers the original question.\n"
            "Output only SQL. No markdown, no comments, no explanation."
        )
        raw = self._llm_text(prompt, system=system)
        return self._extract_sql(raw)

    def _fallback_direct(self, question: str, schema: str) -> str:
        system = "You are a SQL writer. Output only one complete executable SQL query."
        prompt = (
            "Schema:\n"
            f"{schema}\n\n"
            "Question:\n"
            f"{question}\n\n"
            "Write one executable SQL query that answers the question.\n"
            "Output only SQL."
        )
        raw = self._llm_text(prompt, system=system)
        return self._extract_sql(raw)

    def _format_checklist(self, answers) -> str:
        if not answers:
            return "None yet."

        items = []
        for idx, (subquestion, answer) in enumerate(answers, start=1):
            items.append(f"{idx}. {subquestion}\n   Answer: {answer}")

        return "\n".join(items)

    def _clean_lines(self, text: str):
        lines = []

        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()

            if not line or line.startswith("