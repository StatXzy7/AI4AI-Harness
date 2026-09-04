"""Harness that parses the Hint line from the question and enforces it as hard requirements before SQL generation."""

from ..harness_base import SQLHarness
from .. import bridge

import re


class P2P2DQwenS1HintGuard(SQLHarness):
    """Extract the Hint line and make it a non-negotiable part of every SQL prompt."""

    MAX_ATTEMPTS = 5
    SYSTEM = (
        "You are a precise Text-to-SQL engine. Return exactly one executable SQL query. "
        "Never include explanations, Markdown, or code fences. Satisfy all hard requirements."
    )

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        hint = self._extract_hint(question)
        requirements = self._restate_hint_as_requirements(hint)

        prompt = self._initial_prompt(question, hint, requirements)
        raw = self._call_llm(prompt, self.SYSTEM)
        sql = self._extract_sql(raw)

        for attempt in range(self.MAX_ATTEMPTS):
            if not sql:
                prompt = self._missing_sql_prompt(question, hint, requirements, raw)
                raw = self._call_llm(prompt, self.SYSTEM)
                sql = self._extract_sql(raw)
                if not sql:
                    continue

            result = self._safe_execute(sql)
            if result.get("ok"):
                return sql

            if attempt == self.MAX_ATTEMPTS - 1:
                break

            error = result.get("error") or "unknown execution error"
            prompt = self._repair_prompt(question, hint, requirements, sql, error)
            raw = self._call_llm(prompt, self.SYSTEM)
            repaired = self._extract_sql(raw)
            if repaired and repaired.strip():
                sql = repaired.strip()

        return sql if sql.strip() else "SELECT 1"

    def _extract_hint(self, question: str) -> str:
        if not question:
            return ""

        lines = question.splitlines()
        for idx, line in enumerate(lines):
            cleaned = line.strip().lstrip("•-* \t").strip()
            match = re.match(r"(?i)^hint\s*:\s*(.*)$", cleaned)
            if match:
                content = match.group(1).strip()
                if content:
                    return content

                following = []
                for next_line in lines[idx + 1:]:
                    next_clean = next_line.strip()
                    if not next_clean:
                        break
                    if re.match(r"(?i)^(question|schema|hint)\s*:", next_clean):
                        break
                    following.append(next_clean)
                if following:
                    return " ".join(following)

        match = re.search(r"(?i)\bhint\s*:\s*([^\n]+)", question)
        if match:
            return match.group(1).strip()

        return ""

    def _restate_hint_as_requirements(self, hint: str) -> list:
        if not hint:
            return ["No explicit hint was provided. Do not invent extra hint constraints."]

        normalized = re.sub(r"\s+", " ", hint).strip()
        requirements = [f"Hard requirement: satisfy this hint exactly: {normalized}"]
        seen = {normalized.lower()}

        fragments = re.split(r";|\|(?!\|)|(?<=\.)\s+", normalized)
        for fragment in fragments:
            fragment = fragment.strip().strip(".").strip()
            if not fragment:
                continue
            key = fragment.lower()
            if key in seen:
                continue
            seen.add(key)
            requirements.append(f"Hard requirement: {fragment}")

        requirements.append(
            "The hint is mandatory: every constraint above must be reflected in the final SQL."
        )
        return requirements

    def _initial_prompt(self, question: str, hint: str, requirements: list) -> str:
        schema = getattr(self, "schema", "") or ""
        lines = [
            "Generate a single SQL query for the following Text-to-SQL task.",
            "",
            "Schema:",
            schema,
            "",
            "Question:",
            question,
            "",
            "Parsed Hint line:",
            hint if hint else "none",
            "",
            "Hard requirements derived from the Hint:",
        ]
        lines.extend(f"- {item}" for item in requirements)
        lines.extend(
            [
                "",
                "Before writing SQL, treat every hard requirement as non-negotiable.",
                "Return only the SQL query, with no explanation and no Markdown.",
                "Use only tables and columns that exist in the schema.",
            ]
        )
        return "\n".join(lines)

    def _missing_sql_prompt(self, question: str, hint: str, requirements: list, previous_output: str) -> str:
        schema = getattr(self, "schema", "") or ""
        lines = [
            "Your previous response did not contain a usable SQL query.",
            "",
            "Return exactly one SQL query now.",
            "",
            "Schema:",
            schema,
            "",
            "Question:",
            question,
            "",
            "Parsed Hint line:",
            hint if hint else "none",
            "",
            "Hard requirements:",
        ]
        lines.extend(f"- {item}" for item in requirements)
        lines.extend(
            [
                "",
                "Previous response:",
                previous_output or "(empty)",
                "",
                "Respond with only the SQL query.",
            ]
        )
        return "\n".join(lines)

    def _repair_prompt(self, question: str, hint: str, requirements: list, sql: str, error: str) -> str:
        schema = getattr(self, "schema", "") or ""
        lines = [
            "The SQL query below failed execution.",
            "Repair it while preserving all hard requirements.",
            "",
            "Schema:",
            schema,
            "",
            "Question:",
            question,
            "",
            "Parsed Hint line:",
            hint if hint else "none",
            "",
            "Hard requirements:",
        ]
        lines.extend(f"- {item}" for item in requirements)
        lines.extend(
            [
                "",
                "Failed SQL:",
                sql,
                "",
                "Execution error:",
                error,
                "",
                "Return only the corrected SQL query.",
            ]
        )
        return "\n".join(lines)

    def _call_llm(self, prompt: str, system: str) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

        if isinstance(response, (list, tuple)):
            response = response[0] if response else ""

        if isinstance(response, dict):
            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    message = first.get("message")
                    if isinstance(message, dict) and isinstance(message.get("content"), str):
                        return message["content"]
                    if isinstance(first.get("text"), str):
                        return first["text"]

            for key in ("text", "content", "output", "completion"):
                value = response.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            return str(response)

        return str(response or "")

    def _extract_sql(self, text: str) -> str:
        text = str(text or "")

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        if extracted and str(extracted).strip():
            return str(extracted).strip()

        cleaned = text.strip()
        fence = re.search(r"(?is)