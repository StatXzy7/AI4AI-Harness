"""Parses the question's Hint line and restates it as non-negotiable hard requirements before SQL generation."""
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DDeepseekS2HintGuard(SQLHarness):
    def solve(self, question: str) -> str:
        schema = self.schema or ""
        hint = self._extract_hint(question)

        system_prompt = (
            "You are an expert text-to-SQL assistant. "
            "Translate the question into a single valid SQL query for the provided schema. "
            "Treat any stated hard requirements as mandatory constraints."
        )

        if hint:
            user_prompt = (
                f"Database schema:\n{schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Hard requirements extracted from the Hint line (MUST be satisfied):\n{hint}\n\n"
                "Write the SQL query. Ensure the query satisfies every hard requirement above."
            )
        else:
            user_prompt = (
                f"Database schema:\n{schema}\n\n"
                f"Question:\n{question}\n\n"
                "Write the SQL query."
            )

        response = self.llm(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.0,
            n=1,
        )

        return bridge.extract_sql(self._as_text(response))

    @staticmethod
    def _extract_hint(question: str) -> str:
        """Return the content of a Hint: line, if present."""
        if not question:
            return ""

        # First, match a line beginning with Hint:
        for raw_line in question.splitlines():
            line = raw_line.strip()
            match = re.match(r"^Hint\s*:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback: match inline "Hint:" anywhere in a line.
        for raw_line in question.splitlines():
            line = raw_line.strip()
            match = re.search(r"(?:^|\s)Hint\s*:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return ""

    @staticmethod
    def _as_text(response):
        """Normalize an LLM response into a string."""
        if isinstance(response, dict):
            for key in ("text", "content", "message"):
                if response.get(key):
                    return P2P2DDeepseekS2HintGuard._as_text(response[key])
            return ""
        if isinstance(response, (list, tuple)):
            return P2P2DDeepseekS2HintGuard._as_text(response[0]) if response else ""
        if response is None:
            return ""
        return str(response)