"""Parses the Hint line from the question and restates its constraints as hard SQL requirements before generation."""
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        hint = self._extract_hint(question)
        clean_question = self._remove_hint_line(question)

        requirements = self._format_hint_requirements(hint)
        prompt = self._build_prompt(clean_question, requirements)
        system = self._build_system_prompt(hint is not None)

        raw = self._call_llm(prompt, system)
        sql = bridge.extract_sql(raw)

        if not sql:
            fallback_prompt = self._build_fallback_prompt(clean_question, hint)
            raw = self._call_llm(fallback_prompt, system)
            sql = bridge.extract_sql(raw)

        return sql or raw.strip()

    def _extract_hint(self, question: str):
        for line in question.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("hint:"):
                hint = stripped[5:].strip()
                return hint or None
        return None

    def _remove_hint_line(self, question: str) -> str:
        kept = [
            line
            for line in question.splitlines()
            if not line.strip().lower().startswith("hint:")
        ]
        return "\n".join(kept).strip()

    def _format_hint_requirements(self, hint) -> str:
        if not hint:
            return ""
        clauses = [c.strip() for c in re.split(r';\s*', hint) if c.strip()]
        if not clauses:
            clauses = [hint.strip()]
        bullet_lines = "\n".join(f"- {c}" for c in clauses)
        return (
            "HARD REQUIREMENTS extracted from the Hint "
            "(these must be satisfied by the SQL, not optional):\n"
            f"{bullet_lines}\n"
            "Any SQL that violates these hard requirements is invalid."
        )

    def _build_prompt(self, question: str, requirements: str) -> str:
        parts = [
            "Write a SQL query that answers the following question.",
            "Database schema:",
            self.schema or "",
            "",
            "Question:",
            question or "",
            "",
        ]
        if requirements:
            parts.extend([requirements, ""])
        parts.append("Return only the SQL query without any explanation.")
        return "\n".join(parts)

    def _build_fallback_prompt(self, question: str, hint) -> str:
        parts = [
            "You did not return SQL before. Write only the SQL query for this question.",
            "Database schema:",
            self.schema or "",
            "",
            "Question:",
            question or "",
            "",
        ]
        if hint:
            parts.extend([
                "HARD REQUIREMENTS from the Hint (must be obeyed):",
                f"- {hint}",
                "",
            ])
        parts.append("Return only SQL, no surrounding text.")
        return "\n".join(parts)

    def _build_system_prompt(self, has_hint: bool) -> str:
        if has_hint:
            return "You are a SQL expert. Follow all hard requirements exactly and do not ignore them."
        return "You are a SQL expert. Write correct SQLite queries."

    def _call_llm(self, prompt: str, system: str) -> str:
        result = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(result, (list, tuple)):
            if result:
                return str(result[0])
            return ""
        if isinstance(result, dict):
            for key in ("text", "content", "completion"):
                if key in result:
                    return str(result[key])
            return str(result)
        return str(result)