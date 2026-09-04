"""Decomposes the question into ordered sub-questions, answers each with small LLM calls, and assembles a final SQL query."""
from ..harness_base import SQLHarness
from .. import bridge

import json
import re


class P2P2CQwenS0Decompose(SQLHarness):
    MAX_SUBQUESTIONS = 5
    MAX_REPAIR_ATTEMPTS = 2

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        schema = str(getattr(self, "schema", "") or "")

        try:
            subquestions = self._decompose(question, schema)
            qa = []

            for index, subquestion in enumerate(subquestions, 1):
                answer = self._answer_subquestion(index, subquestion, question, schema, qa)
                qa.append((subquestion, answer))

            sql = self._assemble(question, schema, qa)
            return self._validate_and_repair(question, schema, qa, sql)
        except Exception:
            try:
                return self._fallback_sql(question, schema)
            except Exception:
                return "SELECT 1"

    def _llm_text(self, prompt: str, system: str = "") -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except TypeError:
            try:
                response = self.llm(prompt, system, 0.0, 1)
            except TypeError:
                response = self.llm(prompt)
        return self._coerce_text(response)

    def _coerce_text(self, response) -> str:
        if response is None:
            return ""

        if isinstance(response, str):
            return response.strip()

        if isinstance(response, bytes):
            return response.decode("utf-8", "ignore").strip()

        if isinstance(response, (list, tuple)):
            for item in response:
                text = self._coerce_text(item)
                if text:
                    return text
            return ""

        if isinstance(response, dict):
            if "choices" in response and response["choices"] is not None:
                text = self._coerce_text(response["choices"])
                if text:
                    return text

            for key in ("text", "completion", "content", "output", "message", "answer", "result", "data"):
                if key in response:
                    text = self._coerce_text(response[key])
                    if text:
                        return text

            if any(
                key in response
                for key in ("text", "completion", "content", "output", "message", "answer", "result", "choices", "data")
            ):
                return ""

            try:
                return json.dumps(response)
            except Exception:
                return str(response)

        for attr in ("text", "completion", "content", "output", "message", "answer"):
            if hasattr(response, attr):
                value = getattr(response, attr)
                if callable(value):
                    continue
                text = self._coerce_text(value)
                if text:
                    return text

        if hasattr(response, "choices"):
            value = getattr(response, "choices")
            if not callable(value):
                text = self._coerce_text(value)
                if text:
                    return text

        return str(response).strip()

    def _strip_code_fences(self, text: str) -> str:
        if not text:
            return ""

        text = text.strip()
        if text.startswith("