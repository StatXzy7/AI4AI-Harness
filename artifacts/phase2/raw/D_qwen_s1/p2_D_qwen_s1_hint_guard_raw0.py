"""Parses the Hint line from the question and enforces it as explicit hard requirements before SQL generation."""
from ..harness_base import SQLHarness
from .. import bridge

import re


class P2P2DQwenS1HintGuard(SQLHarness):
    SYSTEM_PROMPT = (
        "You are a precise Text-to-SQL engine. Follow every hard requirement exactly. "
        "Return only one SQL query, with no explanation and no markdown."
    )

    HINT_LINE_RE = re.compile(
        r"^\s*hint\s*:\s*(?P<rest>.*)$",
        re.IGNORECASE | re.MULTILINE,
    )
    HINT_INLINE_RE = re.compile(
        r"\bhint\s*:\s*(?P<rest>[^\n]*)",
        re.IGNORECASE,
    )

    def solve(self, question: str) -> str:
        question = question or ""
        hint = self._extract_hint(question)
        hard_requirements = self._make_hard_requirements(hint)

        sql = self._generate_initial_sql(question, hard_requirements)
        sql = self._repair_if_needed(question, sql, hard_requirements)

        return sql or "SELECT 1"

    def _extract_hint(self, question: str) -> str:
        match = self.HINT_LINE_RE.search(question)
        if not match:
            match = self.HINT_INLINE_RE.search(question)

        if not match:
            return ""

        return match.group("rest").strip()

    def _make_hard_requirements(self, hint: str) -> str:
        if not hint:
            return ""

        parts = []
        for chunk in re.split(r"[\n;]+", hint):
            chunk = chunk.strip().strip("-*• \t").strip()
            chunk = re.sub(r"^\d+[.)]\s*", "", chunk).strip()
            chunk = re.sub(
                r"^(must|requirement|constraint)\s*:\s*",
                "",
                chunk,
                flags=re.IGNORECASE,
            ).strip()

            if chunk:
                parts.append(chunk.rstrip("."))

        if not parts:
            parts = [hint.strip()]

        lines = [
            f"{idx}. MUST: {part}"
            for idx, part in enumerate(parts, start=1)
        ]

        return (
            "HARD REQUIREMENTS FROM HINT (non-negotiable; satisfy all of them exactly):\n"
            + "\n".join(lines)
        )

    def _generate_initial_sql(self, question: str, hard_requirements: str) -> str:
        prompt = self._build_generation_prompt(question, hard_requirements)
        raw = self._call_llm(prompt, self.SYSTEM_PROMPT)
        sql = self._extract_sql(raw)

        if sql:
            return sql

        retry_prompt = self._build_generation_prompt(
            question,
            hard_requirements,
            extra_instructions=(
                "Your previous answer did not contain a SQL statement. "
                "Return only a single SQL statement."
            ),
        )
        raw = self._call_llm(retry_prompt, self.SYSTEM_PROMPT)
        sql = self._extract_sql(raw)

        return sql or raw.strip()

    def _build_generation_prompt(
        self,
        question: str,
        hard_requirements: str,
        extra_instructions: str = "",
    ) -> str:
        schema = str(getattr(self, "schema", "") or "")

        sections = [
            f"Schema:\n{schema}",
            f"Question:\n{question.strip()}",
        ]

        if hard_requirements:
            sections.append(hard_requirements)

        if extra_instructions:
            sections.append(extra_instructions)

        sections.append(
            "Write one valid SQL query. Return only SQL, with no markdown and no explanation."
        )

        return "\n\n".join(sections)

    def _repair_if_needed(
        self,
        question: str,
        sql: str,
        hard_requirements: str,
    ) -> str:
        if not sql:
            return sql

        for _ in range(2):
            result = self._safe_execute(sql)

            if result.get("ok"):
                return sql

            error = str(result.get("error") or "unknown execution error")
            prompt = self._build_repair_prompt(
                question,
                sql,
                error,
                hard_requirements,
            )

            raw = self._call_llm(prompt, self.SYSTEM_PROMPT)
            candidate = self._extract_sql(raw) or raw.strip()

            if not candidate or candidate == sql:
                break

            sql = candidate

        return sql

    def _build_repair_prompt(
        self,
        question: str,
        sql: str,
        error: str,
        hard_requirements: str,
    ) -> str:
        schema = str(getattr(self, "schema", "") or "")

        sections = [
            f"Schema:\n{schema}",
            f"Question:\n{question.strip()}",
        ]

        if hard_requirements:
            sections.append(hard_requirements)

        sections.extend(
            [
                f"The following SQL failed:\n{sql}",
                f"Execution error:\n{error}",
                "Rewrite the SQL so it executes correctly and satisfies every hard requirement. "
                "Return only SQL, with no markdown and no explanation.",
            ]
        )

        return "\n\n".join(sections)

    def _safe_execute(self, sql: str) -> dict:
        execute = getattr(self, "execute", None)

        if execute is None:
            return {"ok": True, "rows": [], "error": ""}

        try:
            result = execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return result

        return {"ok": bool(result), "rows": [], "error": ""}

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = None

        if extracted:
            extracted = str(extracted).strip()
            if extracted:
                return extracted

        cleaned = text.strip()
        cleaned = re.sub(r"^