"""Parses a 'Hint:' line from a question, restates its constraints as hard system requirements, and asks the frozen Text-to-SQL solver to return compliant SQL."""
import re
from typing import Any, Optional

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS1HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        hint, cleaned_question = self._parse_hint(question)

        if hint:
            system = (
                "You are a SQL writer. The user's question contained a hint. "
                "The following hard requirements are extracted from that hint and MUST be obeyed:\n"
                f"- {hint}\n"
                "Do not ignore, soften, or omit any of these requirements when generating SQL. "
                "Return only the SQL query."
            )
        else:
            system = (
                "You are a SQL writer. Return only the SQL query that answers the user's question."
            )

        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{cleaned_question}\n\n"
            "Write SQL that answers the question."
        )

        response = self.llm(prompt, system=system, temperature=0.0, n=1)
        response_text = self._response_to_text(response)
        return bridge.extract_sql(response_text)

    @staticmethod
    def _parse_hint(question: str) -> tuple[Optional[str], str]:
        """Extract a line beginning with 'Hint:' and return the hint text and the question without that line."""
        match = re.search(r'^\s*Hint:\s*(.+)$', question, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            return None, question

        hint = match.group(1).strip()
        cleaned = re.sub(
            r'^\s*Hint:\s*.+$',
            '',
            question,
            flags=re.IGNORECASE | re.MULTILINE,
        ).strip()
        return hint, cleaned or question

    @staticmethod
    def _response_to_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        if isinstance(response, list):
            return str(response[0]) if response else ""
        if isinstance(response, dict):
            for key in ("text", "content", "message", "output"):
                if key in response:
                    return str(response[key])
        return str(response)