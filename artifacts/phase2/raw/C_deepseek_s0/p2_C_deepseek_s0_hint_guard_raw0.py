"""Parses a 'Hint:' line from the question and restates its constraints as hard requirements before generating SQL."""
import re
from typing import List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CDeepseekS0HintGuard(SQLHarness):
    """Harness that enforces hints as hard requirements before SQL generation."""

    @staticmethod
    def _extract_hints(question: str) -> List[str]:
        hints = []
        for raw_line in question.splitlines():
            line = raw_line.strip()
            match = re.match(r"^Hint\s*:\s*(.+)$", line, re.IGNORECASE)
            if match:
                hint = match.group(1).strip()
                if hint:
                    hints.append(hint)
        return hints

    def _build_prompt(self, question: str, hard_requirements: str) -> str:
        parts = []
        schema = getattr(self, "schema", "")
        parts.append(f"Database schema:\n{schema}")
        parts.append(f"Question:\n{question}")
        if hard_requirements:
            parts.append(
                "Hard requirements extracted from the Hint line (these must all be satisfied):\n"
                f"{hard_requirements}"
            )
        parts.append(
            "Write a single SQL query that answers the question and satisfies all stated hard requirements. "
            "Return only the SQL query."
        )
        return "\n\n".join(parts)

    def solve(self, question: str) -> str:
        hints = self._extract_hints(question)
        hard_requirements = "; ".join(hints)

        system = ""
        if hard_requirements:
            system = (
                "You are a precise text-to-SQL assistant. The hard requirements in the prompt are mandatory. "
                "Obey them exactly; they override any conflicting implication in the question."
            )

        prompt = self._build_prompt(question, hard_requirements)

        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        raw = raw or ""

        final_sql_string = bridge.extract_sql(raw)
        if not final_sql_string:
            final_sql_string = raw.strip()
        return final_sql_string