"""Parses the question's Hint line and turns it into hard requirements that are enforced before SQL generation."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CQwenS0HintGuard(SQLHarness):
    _HINT_LINE_RE = re.compile(r"^\s*hint\s*[:\-]\s*(?P<hint>.*)$", re.IGNORECASE)
    _HINT_INLINE_RE = re.compile(r"\bhint\s*[:\-]\s*", re.IGNORECASE)
    _SQL_FALLBACK_RE = re.compile(r"(?is)\b(select|with)\b.*")

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        clean_question, hint = self._split_hint(question)
        requirements = self._hard_requirements_from_hint(hint)

        system = (
            "You are a precise Text-to-SQL engine. You must follow the schema, the question, and every hard requirement exactly. "
            "Return only SQL."
        )

        prompt = self._build_prompt(clean_question, hint, requirements)
        raw = self._call_llm(prompt, system)
        sql = self._extract_sql(raw)

        tried = set()
        last_error = ""
        max_attempts = 2

        for attempt in range(max_attempts):
            if sql:
                if sql in tried:
                    break
                tried.add(sql)
                result = self._execute_sql(sql)
                if result.get("ok"):
                    return sql
                last_error = result.get("error") or "Execution failed"
            else:
                last_error = "No SQL was extracted from the model response."

            if attempt == max_attempts - 1:
                break

            prompt = self._build_prompt(
                clean_question,
                hint,
                requirements,
                mode="repair",
                previous_sql=sql,
                previous_error=last_error,
                previous_raw=raw,
            )
            raw = self._call_llm(prompt, system)
            new_sql = self._extract_sql(raw)

            if not new_sql or new_sql == sql:
                sql = new_sql or sql
                break

            sql = new_sql

        return sql or ""

    def _split_hint(self, question: str):
        hints = []
        kept_lines = []

        for line in question.splitlines():
            line_hint = self._HINT_LINE_RE.match(line)
            if line_hint:
                hint_text = line_hint.group("hint").strip()
                if hint_text:
                    hints.append(hint_text)
                continue

            inline_hint = self._HINT_INLINE_RE.search(line)
            if inline_hint and inline_hint.start() > 0:
                prefix = line[: inline_hint.start()].strip(" \t-•*")
                hint_text = line[inline_hint.end():].strip()
                if prefix:
                    kept_lines.append(prefix)
                if hint_text:
                    hints.append(hint_text)
                continue

            kept_lines.append(line)

        hint = " ".join(hints).strip()
        clean_question = "\n".join(kept_lines).strip()

        if not clean_question:
            clean_question = self._HINT_INLINE_RE.sub("", question).strip()

        return clean_question, hint

    def _hard_requirements_from_hint(self, hint: str):
        if not hint:
            return []

        text = " ".join(hint.split())
        segments = re.split(
            r"[;；。|]+|(?<=[a-z0-9])\.(?=\s|$)",
            text,
            flags=re.IGNORECASE,
        )

        requirements = []
        for segment in segments:
            segment = segment.strip().strip(".").strip()
            segment = re.sub(r"^(?:[-*\u2022]|\d+[.)])\s*", "", segment).strip()
            if not segment:
                continue
            segment = " ".join(segment.split())
            requirements.append(f"MUST satisfy: {segment}")

        if not requirements:
            requirements.append(f"MUST satisfy: {text}")

        unique = []
        seen = set()
        for requirement in requirements:
            key = requirement.lower()
            if key not in seen:
                seen.add(key)
                unique.append(requirement)

        return unique

    def _build_prompt(
        self,
        clean_question: str,
        hint: str,
        requirements,
        mode: str = "initial",
        previous_sql: str = "",
        previous_error: str = "",
        previous_raw: str = "",
    ) -> str:
        schema = (getattr(self, "schema", "") or "").strip()

        parts = [
            "Task: produce one final SQL query for the given schema and question.",
        ]

        if schema:
            parts.append("Schema:\n" + schema)

        if clean_question:
            parts.append("Question:\n" + clean_question)

        if hint:
            parts.append("Hint (binding):\n" + hint)

        if requirements:
            parts.append("HARD REQUIREMENTS derived from the Hint:")
            parts.extend(f"- {requirement}" for requirement in requirements)
            parts.append("Satisfy every HARD REQUIREMENT before writing the SQL.")
        else:
            parts.append("There are no additional Hint-derived hard requirements.")

        if mode == "repair":
            if previous_sql:
                parts.append("Previous SQL:\n" + previous_sql)
            else:
                parts.append("Previous response did not contain an extractable SQL statement.")
                if previous_raw:
                    parts.append("Previous response (truncated):\n" + previous_raw.strip()[:500])

            if previous_error:
                parts.append("Previous problem:\n" + str(previous_error))

            parts.append(
                "Rewrite the answer as one executable SQL statement that satisfies all HARD REQUIREMENTS."
            )

        parts.append("Output only the SQL statement. No markdown, no explanation.")
        return "\n\n".join(parts)

    def _call_llm(self, prompt: str, system: str) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        return self._response_to_text(response)

    def _response_to_text(self, response) -> str:
        if response is None:
            return ""

        if isinstance(response, (list, tuple)):
            return "\n".join(self._response_to_text(item) for item in response).strip()

        if isinstance(response, dict):
            for key in ("text", "completion", "content", "message", "sql", "output"):
                if key in response:
                    return self._response_to_text(response[key])
            if "choices" in response:
                return self._response_to_text(response["choices"])
            return str(response)

        return str(response)

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        if sql:
            return str(sql).strip()

        candidate = text.strip()
        if candidate.startswith("