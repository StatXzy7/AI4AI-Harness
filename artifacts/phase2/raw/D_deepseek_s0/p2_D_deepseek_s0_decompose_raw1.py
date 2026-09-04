"""Break a question into ordered sub-questions, answer each with a small LLM call, then assemble the final SQL."""

import re
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS0Decompose(SQLHarness):
    def _call_llm(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, list):
            return str(out[0]) if out else ""
        return str(out) if out else ""

    def _parse_list(self, text: str):
        if not text:
            return []
        text = text.strip()
        if text.startswith("