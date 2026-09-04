"""Parse the 'Hint:' line from the question and restate its constraints as hard requirements before generating SQL."""

import re
from typing import Optional

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS2HintGuard(SQLHarness):
    _HINT_RE = re.compile(r'(?im)^\s*Hint\s*:\s*(.+?)\s*$')
    _SYSTEM_PROMPT = (
        "You are an expert SQL developer. "
        "Return only the SQL query as plain text, no markdown, explanations, or extra text."
    )

    def solve(self, question: str) -> str:
        hint = self._extract_hint(question)
        prompt = self._build_prompt(question, hint)
        response = self.llm(prompt, system=self._SYSTEM_PROMPT, temperature=0.0, n=1)
        sql = bridge.extract_sql(response)
        return sql or ""

    def _extract_hint(self, question: str) -> Optional[str]:
        match = self._HINT_RE.search(question)
        if not match:
            return None
        return match.group(1).strip()

    def _restate_hint_as_hard_requirements(self, hint: str) -> str:
        return (
            "Extracted hint constraints are HARD REQUIREMENTS. "
            "The SQL must satisfy all of them:\n"
            f"* {hint}\n"
            "Do not ignore, weaken, or omit any hint constraint."
        )

    def _build_prompt(self, question: str, hint: Optional[str]) -> str:
        prompt = (
            "You are given a database schema and a natural language question. "
            "Generate one SQL query that answers the question.\n\n"
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n"
        )
        if hint:
            prompt += "\n" + self._restate_hint_as_hard_requirements(hint) + "\n"
        prompt += "\nWrite only the SQL query."
        return prompt