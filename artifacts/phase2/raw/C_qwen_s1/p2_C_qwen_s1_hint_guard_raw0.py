"""Parse the Hint line from the question and enforce its clauses as explicit hard requirements before SQL generation."""

from ..harness_base import SQLHarness
from .. import bridge

import re


class P2P2CQwenS1HintGuard(SQLHarness):
    _HINT_LINE_RE = re.compile(
        r"^\s*(?:[-*]\s*)?hint\s*:\s*(?P<hint>.+?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    _HINT_INLINE_RE = re.compile(
        r"\bhint\s*:\s*(?P<hint>[^\n]+)",
        re.IGNORECASE,
    )
    _HINT_LINE_DROP_RE = re.compile(
        r"^\s*(?:[-*]\s*)?hint\s*:\s*",
        re.IGNORECASE,
    )
    _READ_ONLY_PREFIXES = (
        "select",
        "with",
        "pragma",
        "show",
        "describe",
        "explain",
    )

    def solve(self, question: str) -> str:
        question = str(question or "").strip()

        hint_lines = self._extract_hint_lines(question)
        requirements = self._build_hard_requirements(hint_lines)
        clean_question = self._remove_hint_lines(question)

        system = (
            "You are a precise Text-to-SQL engine. "
            "Return only one complete SQL statement without explanations."
        )

        prompt = self._initial_prompt(clean_question, hint_lines, requirements)
        sql = self._extract_sql(self._llm_text(prompt, system))

        if not sql:
            sql = self._fallback_sql(clean_question, requirements, system)

        best_sql = sql

        # Guard/repair loop: validate against the database only for read-only-looking SQL.
        for _ in range(2):
            if not best_sql:
                break

            result = self._safe_execute(best_sql)
            if result is None:
                break

            if result.get("ok"):
                return best_sql

            error = str(result.get("error") or "").strip()
            if not error:
                break

            repaired = self._repair_sql(
                clean_question,
                requirements,
                best_sql,
                error,
                system,
            )

            if not repaired or repaired == best_sql:
                break

            best_sql = repaired

        return best_sql

    def _extract_hint_lines(self, question: str):
        matches = []

        for match in self._HINT_LINE_RE.finditer(question):
            hint = match.group("hint").strip()
            if hint:
                matches.append(hint)

        if not matches:
            for match in self._HINT_INLINE_RE.finditer(question):
                hint = match.group("hint").strip()
                if hint:
                    matches.append(hint)

        return self._dedupe(matches)

    def _remove_hint_lines(self, question: str) -> str:
        lines = question.splitlines()
        kept = [line for line in lines if not self._HINT_LINE_DROP_RE.match(line)]
        cleaned = "\n".join(kept).strip()
        return cleaned or question.strip()

    def _build_hard_requirements(self, hint_lines):
        requirements = []

        for hint in hint_lines:
            for clause in self._split_hint_clauses(hint):
                requirements.append(f"MUST satisfy this hint constraint: {clause}.")

        return self._dedupe(requirements)

    def _split_hint_clauses(self, hint: str):
        text = (hint or "").strip()
        if not text:
            return []

        parts = re.split(r"[;]\s*|\n+|(?<=[.!?])\s+", text)
        clauses = []

        for part in parts:
            part = part.strip().strip('"\'`').strip()
            part = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", part)
            part = part.strip().rstrip(".!?").strip()

            if not part:
                continue

            if part[0].isalpha() and part[0].islower():
                part = part[0].upper() + part[1:]

            clauses.append(part)

        if not clauses:
            clause = text.rstrip(".!?").strip()
            if clause:
                clauses.append(clause)

        return clauses

    def _initial_prompt(self, question: str, hint_lines, requirements) -> str:
        schema = getattr(self, "schema", "") or ""
        hint_block = "\n".join(f"- {hint}" for hint in hint_lines) if hint_lines else "None"
        requirement_block = self._format_requirements(requirements)

        return f"""Write one SQL query that answers the question.

Database schema:
{schema}

Question:
{question}

Parsed Hint line(s):
{hint_block}

Hard requirements derived from the hint (non-negotiable; satisfy all before writing SQL):
{requirement_block}

Return only the final SQL query, with no markdown and no explanation.
"""

    def _fallback_sql(self, question: str, requirements, system: str) -> str:
        schema = getattr(self, "schema", "") or ""
        requirement_block = self._format_requirements(requirements)

        prompt = f"""Write one SQL query that answers the question.

Database schema:
{schema}

Question:
{question}

Hard requirements:
{requirement_block}

Return only the final SQL query.
"""

        raw = self._llm_text(prompt, system)
        return self._extract_sql(raw)

    def _repair_sql(
        self,
        question: str,
        requirements,
        sql: str,
        error: str,
        system: str,
    ) -> str:
        schema = getattr(self, "schema", "") or ""
        requirement_block = self._format_requirements(requirements)

        prompt = f"""The following SQL query failed execution.

Database schema:
{schema}

Question:
{question}

Hard requirements derived from the hint (non-negotiable):
{requirement_block}

Previous SQL:
{sql}

Execution error:
{error}

Rewrite the query so it executes successfully and satisfies all hard requirements.
Return only the corrected SQL query.
"""

        raw = self._llm_text(prompt, system)
        return self._extract_sql(raw)

    def _format_requirements(self, requirements) -> str:
        if not requirements:
            return "No explicit hint constraints were parsed."

        return "\n".join(
            f"{i}. {requirement}"
            for i, requirement in enumerate(requirements, 1)
        )

    def _safe_execute(self, sql: str):
        if not self._looks_read_only(sql):
            return None

        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if result is None:
            return None

        if isinstance(result, dict):
            return result

        return {"ok": True, "rows": [], "error": ""}

    def _looks_read_only(self, sql: str) -> bool:
        text = (sql or "").strip()
        if not text:
            return False

        text = re.sub(
            r"^\s*(?:--[^\n]*\n|/\*.*?\*/)+",
            "",
            text,
            flags=re.S,
        )
        text = text.strip().lower()

        return text.startswith(self._READ_ONLY_PREFIXES)

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        if extracted and str(extracted).strip():
            return str(extracted).strip()

        return str(text).strip()

    def _llm_text(self, prompt: str, system: str) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        return self._stringify_response(response)

    def _stringify_response(self, response) -> str:
        if response is None:
            return ""

        if isinstance(response, list):
            response = response[0] if response else ""

        if isinstance(response, dict):
            for key in (
                "sql",
                "text",
                "completion",
                "content",
                "message",
                "output",
                "response",
            ):
                value = response.get(key)

                if isinstance(value, str) and value.strip():
                    return value

                if isinstance(value, dict):
                    content = value.get("content") or value.get("text")
                    if isinstance(content, str) and content.strip():
                        return content

            return str(response)

        if hasattr(response, "content"):
            content = response.content
            if isinstance(content, str):
                return content

        if hasattr(response, "text"):
            text = response.text
            if isinstance(text, str):
                return text

        return str(response)

    def _dedupe(self, items):
        seen = set()
        result = []

        for item in items:
            key = str(item).strip().lower()
            if key and key not in seen:
                seen.add(key)
                result.append(item)

        return result