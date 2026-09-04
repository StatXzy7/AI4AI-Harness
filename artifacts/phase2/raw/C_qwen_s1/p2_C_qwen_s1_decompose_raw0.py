"""Decomposes the question into ordered sub-questions, answers each with small LLM calls, then assembles and repairs the final SQL."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS1Decompose(SQLHarness):
    MAX_SUBQUESTIONS = 5
    MAX_REPAIRS = 3

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        schema = str(getattr(self, "schema", "") or "")

        # 1. Decompose the user question into ordered sub-questions.
        subquestions = self._decompose(question, schema)

        # 2. Answer each sub-question with a small LLM call.
        context = []
        for idx, subq in enumerate(subquestions, 1):
            answer, fragment = self._answer_subquestion(idx, subq, question, schema, context)
            context.append(
                {
                    "sub_question": subq,
                    "answer": answer,
                    "sql_fragment": fragment,
                }
            )

        # 3. Assemble the final SQL from the intermediate answers.
        final_sql = self._assemble(question, schema, context)
        final_sql = self._repair_loop(final_sql, question, schema, context)

        # 4. If assembly still fails, fall back to a direct generation path.
        ok, _ = self._execute_sql(final_sql)
        if not ok:
            direct_sql = self._direct_sql(question, schema, context)
            direct_sql = self._repair_loop(direct_sql, question, schema, context)
            direct_ok, _ = self._execute_sql(direct_sql)

            if direct_ok or not final_sql:
                final_sql = direct_sql
            elif direct_sql:
                final_sql = direct_sql

        if not final_sql:
            final_sql = "SELECT 1"

        return final_sql.strip()

    def _llm_text(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            return ""
        return self._coerce_text(response)

    def _coerce_text(self, response) -> str:
        if response is None:
            return ""

        if isinstance(response, bytes):
            return response.decode("utf-8", "ignore").strip()

        if isinstance(response, str):
            return response.strip()

        if isinstance(response, (list, tuple)):
            return self._coerce_text(response[0]) if response else ""

        if isinstance(response, dict):
            for key in ("text", "completion", "content", "output", "result"):
                if key in response:
                    return self._coerce_text(response[key])

            if "choices" in response:
                choices = response.get("choices")
                if isinstance(choices, (list, tuple)) and choices:
                    first = choices[0]
                    if isinstance(first, dict):
                        if "message" in first:
                            return self._coerce_text(first["message"])
                        if "text" in first:
                            return self._coerce_text(first["text"])

            return str(response).strip()

        if hasattr(response, "choices"):
            try:
                choices = getattr(response, "choices", [])
                if choices:
                    first = choices[0]

                    if isinstance(first, dict):
                        if "message" in first:
                            return self._coerce_text(first["message"])
                        if "text" in first:
                            return self._coerce_text(first["text"])

                    if hasattr(first, "message"):
                        return self._coerce_text(getattr(first.message, "content", ""))

                    if hasattr(first, "text"):
                        return self._coerce_text(getattr(first, "text", ""))
            except Exception:
                pass

        return str(response).strip()

    def _extract_sql(self, text: str) -> str:
        text = str(text or "")

        extracted = ""
        try:
            extracted = str(bridge.extract_sql(text) or "").strip()
        except Exception:
            extracted = ""

        if extracted:
            cleaned = self._clean_sql(extracted)
            if cleaned:
                return cleaned

        cleaned = self._clean_sql(text)
        if cleaned and re.search(r"\b(?:SELECT|WITH)\b", cleaned, re.IGNORECASE):
            cleaned = self._remove_label_lines(cleaned)
            if cleaned:
                return self._clean_sql(cleaned)

        return ""

    def _clean_sql(self, text: str) -> str:
        text = str(text or "").strip()
        if not text:
            return ""

        text = re.sub(r"