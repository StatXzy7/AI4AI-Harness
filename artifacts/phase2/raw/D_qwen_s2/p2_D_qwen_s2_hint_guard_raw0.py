"""Harness that parses a Hint line from the question and enforces it as explicit hard requirements before SQL generation."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS2HintGuard(SQLHarness):
    _HINT_LINE_RE = re.compile(r"(?im)^[ \t]*hint[ \t]*:[ \t]*(?P<hint>.*)$")
    _HINT_INLINE_RE = re.compile(r"(?i)\bhint[ \t]*:[ \t]*(?P<hint>[^\n]+)")
    _REMOVE_HINT_LINE_RE = re.compile(r"(?im)^[ \t]*hint[ \t]*:[^\n]*\n?")

    def solve(self, question: str) -> str:
        question = question or ""

        hint = self._extract_hint(question)
        guarded_question = self._remove_hint_lines(question) if hint else question
        requirements = self._hint_to_hard_requirements(hint)

        prompt = self._build_sql_prompt(guarded_question, requirements)
        system = (
            "You are a precise Text-to-SQL generator. Every hard requirement must be satisfied. "
            "Return only one SQL statement."
        )

        response = self._call_llm(prompt, system)
        sql = self._extract_sql(response)

        if not sql:
            retry_prompt = (
                prompt
                + "\n\nThe previous answer did not contain a clean SQL statement. "
                "Return ONLY the SQL statement. No markdown, no explanation."
            )
            response = self._call_llm(retry_prompt, system)
            sql = self._extract_sql(response)

        if not sql:
            sql = response.strip() if response else ""

        return sql

    def _extract_hint(self, question: str) -> str:
        hints = []

        for match in self._HINT_LINE_RE.finditer(question):
            value = match.group("hint").strip()
            if value:
                hints.append(value)

        if not hints:
            for match in self._HINT_INLINE_RE.finditer(question):
                value = match.group("hint").strip()
                if value:
                    hints.append(value)

        return "; ".join(hints)

    def _remove_hint_lines(self, question: str) -> str:
        cleaned = self._REMOVE_HINT_LINE_RE.sub("", question).strip()
        return cleaned or question.strip()

    def _hint_to_hard_requirements(self, hint: str):
        if not hint:
            return []

        parts = re.split(r"[;\n]+", hint)
        requirements = []

        for part in parts:
            part = part.strip().strip(".").strip()
            if part:
                requirements.append(part)

        if not requirements:
            requirements = [hint.strip()]

        return requirements

    def _build_sql_prompt(self, question: str, requirements):
        schema = getattr(self, "schema", "") or ""
        sections = []

        sections.append("Generate a single SQL query for the following question.")
        sections.append(f"Schema:\n{schema}")
        sections.append(f"Question:\n{question}")

        if requirements:
            lines = ["HARD REQUIREMENTS (derived from the Hint line; all are mandatory):"]
            for idx, requirement in enumerate(requirements, 1):
                lines.append(f"{idx}. MUST: {requirement}")
            lines.append("Do not ignore, weaken, or contradict any hard requirement.")
            sections.append("\n".join(lines))

        sections.append(
            "Write only the SQL statement. Do not include explanations, markdown fences, or comments."
        )

        return "\n\n".join(sections)

    def _call_llm(self, prompt: str, system: str) -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        return self._response_to_text(response)

    def _response_to_text(self, response) -> str:
        if response is None:
            return ""

        if isinstance(response, str):
            return response

        if isinstance(response, list):
            return "\n".join(self._response_to_text(item) for item in response)

        if isinstance(response, dict):
            for key in ("text", "content", "completion", "message", "choices"):
                if key in response:
                    return self._response_to_text(response[key])
            return str(response)

        return str(response)

    def _extract_sql(self, text: str) -> str:
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        return (sql or "").strip()