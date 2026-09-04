"""Parses a `Hint:` line from the question and converts it into explicit hard constraints before generating SQL."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        hints = self._extract_hints(question)
        hard_requirements = self._format_hard_requirements(hints)

        system = (
            "You are a disciplined SQL writer. Treat every stated hard requirement as "
            "a mandatory constraint. Do not ignore or weaken any constraint."
        )
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            f"{hard_requirements}"
            "Write a single SQL query that answers the question and satisfies all hard requirements. "
            "Return only the SQL query."
        )

        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        if isinstance(raw, dict):
            raw = raw.get("text") or raw.get("content") or ""

        sql = bridge.extract_sql(str(raw or ""))
        return sql if sql else str(raw or "").strip()

    def _extract_hints(self, question: str):
        hints = []
        for line in question.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            for prefix in ("hint:", "hints:"):
                if lower.startswith(prefix):
                    hint = stripped[len(prefix):].strip()
                    if hint:
                        hints.append(hint)
                    break
        return hints

    def _format_hard_requirements(self, hints):
        if not hints:
            return ""
        lines = ["HARD REQUIREMENTS (must satisfy all):"]
        lines += [f"- {hint}" for hint in hints]
        lines.append("")
        return "\n".join(lines)