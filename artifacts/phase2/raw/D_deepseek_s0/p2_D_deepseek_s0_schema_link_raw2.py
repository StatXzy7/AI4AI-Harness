"""A two-stage harness that links schema elements to the question before generating Text-to-SQL."""
import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS0SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        relevant = self._identify_relevant_entities(question)
        linked_schema = self._project_schema(relevant)
        return self._write_sql(question, linked_schema)

    # ------------------------------------------------------------------
    # LLM call helper
    # ------------------------------------------------------------------
    def _call_llm(self, prompt: str, system: str = "", temperature: float = 0.0, n: int = 1) -> str:
        resp = self.llm(prompt, system=system, temperature=temperature, n=n)

        if isinstance(resp, str):
            return resp

        if isinstance(resp, dict):
            for key in ("content", "text", "message"):
                if key in resp:
                    return str(resp[key])
            return str(resp)

        content = getattr(resp, "content", None)
        if content is not None:
            return str(content)

        if hasattr(resp, "choices"):
            try:
                choices = resp.choices
                if choices:
                    choice = choices[0]
                    if hasattr(choice, "message"):
                        return str(choice.message.content)
                    if hasattr(choice, "text"):
                        return str(choice.text)
            except Exception:
                pass

        return str(resp)

    # ------------------------------------------------------------------
    # Schema linking stage
    # ------------------------------------------------------------------
    def _identify_relevant_entities(self, question: str) -> dict:
        prompt = (
            "You are given a natural language question and a database schema.\n"
            "Your task is to identify the tables and columns needed to answer the question.\n\n"
            f"Question:\n{question}\n\n"
            f"Database schema:\n{self.schema}\n\n"
            "Return a JSON object mapping each relevant table name to a list of relevant column names. "
            "Use exactly the table and column names as they appear in the schema. "
            "If an entire table is relevant, list all of its columns. "
            "Only include information needed for this question.\n\n"
            "Return ONLY valid JSON, without markdown fences or commentary."
        )
        raw = self._call_llm(prompt, system="You are a precise database schema linker.")
        linked = self._parse_linked_entities(raw)

        if not linked:
            linked = self._fallback_linked_entities(question)

        return linked

    def _parse_linked_entities(self, raw: str) -> dict:
        if not raw:
            return {}

        text = self._strip_markdown_json(raw)

        try:
            data = json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and start < end:
                try:
                    data = json.loads(text[start:end + 1])
                except Exception:
                    return {}
            else:
                return {}

        return self._normalize_entities(data)

    @staticmethod
    def _strip_markdown_json(text: str) -> str:
        text = text.strip()
        if text.startswith("