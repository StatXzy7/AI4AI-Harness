"""Parses the Hint line from the question and restates its constraints as hard requirements before asking the frozen solver to write SQL."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS0HintGuard(SQLHarness):
    """Make Hint constraints explicit hard requirements before SQL generation."""

    _HINT_LINE_RE = re.compile(
        r"^\s*hint\s*:\s*(?P<hint>.+?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    _HINT_INLINE_RE = re.compile(
        r"\bhint\s*:\s*(?P<hint>[^\n]+)",
        re.IGNORECASE,
    )
    _CLAUSE_SPLIT_RE = re.compile(
        r"\s*(?:;|\n|(?<=[.!?])\s+)\s*",
    )
    _LIST_PREFIX_RE = re.compile(
        r"^\s*(?:[-*•]|\d+[.)])\s+",
    )

    def solve(self, question: str) -> str:
        question = question or ""

        hint = self._extract_hint(question)
        core_question = self._remove_hint(question)
        requirements = self._build_requirements(hint)

        prompt = self._build_prompt(core_question, hint, requirements)
        system = (
            "You are a precise Text-to-SQL engine. "
            "You obey schema constraints exactly and output only one executable SQL statement."
        )

        response_text = self._call_llm(prompt, system)
        sql = self._extract_sql(response_text)

        if not sql:
            retry_prompt = (
                prompt
                + "\n\nYour previous reply did not contain a clear SQL statement. "
                "Return only the SQL statement, with no markdown and no explanation."
            )
            response_text = self._call_llm(retry_prompt, system)
            sql = self._extract_sql(response_text)

        return sql or (response_text or "").strip()

    def _extract_hint(self, question):
        match = self._HINT_LINE_RE.search(question)
        if not match:
            match = self._HINT_INLINE_RE.search(question)

        if not match:
            return ""

        return match.group("hint").strip().strip('"\'').strip()

    def _remove_hint(self, question):
        cleaned = self._HINT_LINE_RE.sub("", question)
        cleaned = self._HINT_INLINE_RE.sub("", cleaned)

        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        cleaned = "\n".join(lines).strip()

        return cleaned or "Answer the request using the provided schema and the hard requirements below."

    def _build_requirements(self, hint):
        requirements = []

        if hint:
            for idx, part in enumerate(self._split_hint(hint), start=1):
                requirements.append(
                    f"{idx}. The SQL MUST satisfy this hint constraint: {part}"
                )

            requirements.append(
                f"{len(requirements) + 1}. Treat the entire Hint line as non-negotiable: {hint}."
            )
            requirements.append(
                f"{len(requirements) + 1}. Interpret each hint constraint as a concrete SQL operation "
                "or predicate, not as optional guidance."
            )
        else:
            requirements.append(
                "1. No explicit Hint is present; answer the question exactly."
            )

        requirements.append(
            f"{len(requirements) + 1}. Use only tables and columns that exist in the schema."
        )
        requirements.append(
            f"{len(requirements) + 1}. Produce one executable SQL statement, without explanation."
        )

        return requirements

    def _split_hint(self, hint):
        parts = self._CLAUSE_SPLIT_RE.split(hint.strip())
        cleaned = []

        for part in parts:
            part = self._LIST_PREFIX_RE.sub("", part.strip()).strip()
            part = part.strip(";").strip()

            if not part:
                continue

            if not part.endswith((".", "!", "?")):
                part += "."

            cleaned.append(part)

        if not cleaned and hint.strip():
            cleaned = [hint.strip()]

        unique = []
        seen = set()

        for part in cleaned:
            key = part.lower()
            if key not in seen:
                seen.add(key)
                unique.append(part)

        return unique

    def _build_prompt(self, core_question, hint, requirements):
        req_block = "\n".join(requirements)
        hint_block = hint if hint else "No explicit Hint line was found."

        return (
            "Generate SQL for the following question.\n"
            "\n"
            f"SCHEMA:\n{self.schema}\n"
            "\n"
            f"QUESTION:\n{core_question}\n"
            "\n"
            f"PARSED HINT:\n{hint_block}\n"
            "\n"
            f"HARD REQUIREMENTS:\n{req_block}\n"
            "\n"
            "Before writing SQL, check that every hard requirement is covered. "
            "Then return only the final SQL statement."
        )

    def _call_llm(self, prompt, system):
        result = self.llm(prompt, system=system, temperature=0.0, n=1)

        if isinstance(result, list):
            return str(result[0]) if result else ""

        if isinstance(result, dict):
            for key in ("text", "completion", "content", "response", "output"):
                value = result.get(key)
                if isinstance(value, str) and value:
                    return value
            return str(result)

        return str(result)

    def _extract_sql(self, text):
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        return (extracted or "").strip()