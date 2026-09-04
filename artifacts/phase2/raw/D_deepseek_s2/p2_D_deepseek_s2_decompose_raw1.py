"""Decompose a Text-to-SQL question into ordered sub-questions, answer each with a small LLM call, then assemble the final SQL."""
from ..harness_base import SQLHarness
from .. import bridge
import json
import re


class P2P2DDeepseekS2Decompose(SQLHarness):
    def _llm_text(self, prompt: str, system: str = "") -> str:
        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(response, list):
            return response[0] if response else ""
        return str(response)

    def _parse_json_list(self, text: str):
        text = text.strip()
        text = re.sub(r"^