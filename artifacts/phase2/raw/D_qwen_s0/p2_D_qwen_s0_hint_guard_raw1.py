"""Parse the Hint line from the question and enforce it as hard requirements before generating SQL."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DQwenS0HintGuard(SQLHarness):
    MAX_ATTEMPTS = 3
    FALLBACK_SQL = "SELECT 1"

    def solve(self, question: str) -> str:
        question = question or ""
        hint = self._extract_hint(question)
        requirements = self._build_requirements(hint)
        system = self._system_prompt(hint)

        best_sql = self.FALLBACK_SQL
        last_error = ""

        for attempt in range(self.MAX_ATTEMPTS):
            prior_sql = None if attempt == 0 else best_sql
            error = last_error if attempt else ""

            prompt = self._build_prompt(
                question=question,
                hint=hint,
                requirements=requirements,
                prior_sql=prior_sql,
                error=error,
            )

            raw_response = self._call_llm(prompt, system)
            sql = self._extract_sql(raw_response)

            if not sql:
                last_error = "No SQL could be extracted from the model response."
                continue

            best_sql = sql
            result = self._execute_sql(sql)

            if result.get("ok"):
                return sql

            last_error = str(result.get("error") or "SQL execution failed")

        return best_sql

    def _extract_hint(self, question: str) -> str:
        lines = question.splitlines()

        hint_line_re = re.compile(
            r"^\s*(?:[-*]|\d+[.)])?\s*hint\s*:\s*(.*)$",
            re.IGNORECASE,
        )
        inline_hint_re = re.compile(r"\bhint\s*:\s*(.*)$", re.IGNORECASE)

        for i, line in enumerate(lines):
            match = hint_line_re.match(line)
            if match is None:
                match = inline_hint_re.search(line)

            if match is None:
                continue

            text = match.group(1).strip()

            if not text:
                for following in lines[i + 1 :]:
                    following = following.strip()
                    if following:
                        text = following
                        break

            if text:
                return text

        return ""

    def _build_requirements(self, hint: str):
        if not hint:
            return []

        requirements = [
            f"The parsed hint is mandatory: {hint}",
        ]

        for constraint in self._split_constraints(hint):
            requirements.append(f"Hard requirement from hint: {constraint}")

        requirements.extend(
            [
                "Every constraint restated above must be enforced exactly in the SQL.",
                "Do not ignore, weaken, or reinterpret the hint.",
                "If the question and the hint conflict, the hint wins.",
            ]
        )

        return requirements

    def _split_constraints(self, hint: str):
        parts = re.split(r";|\n|(?<=\.)\s+", hint)
        constraints = []

        for part in parts:
            part = part.strip().strip(".").strip()
            if part:
                constraints.append(part)

        return constraints or [hint]

    def _system_prompt(self, hint: str) -> str:
        if hint:
            return (
                "You are a precise text-to-SQL generator. A hint was parsed from the question. "
                "Treat the hint as a set of hard requirements that must be enforced in the SQL. "
                "Return only one executable SQL statement."
            )

        return (
            "You are a precise text-to-SQL generator. "
            "Return only one executable SQL statement."
        )

    def _build_prompt(self, question, hint, requirements, prior_sql=None, error=""):
        sections = []

        sections.append("SCHEMA:")
        sections.append(str(getattr(self, "schema", "") or ""))
        sections.append("")

        sections.append("QUESTION:")
        sections.append(question)
        sections.append("")

        if hint:
            sections.append("PARSED HINT:")
            sections.append(hint)
            sections.append("")

            sections.append("HARD REQUIREMENTS RESTATED FROM HINT:")
            for i, requirement in enumerate(requirements, 1):
                sections.append(f"{i}. {requirement}")
            sections.append("")
        else:
            sections.append("PARSED HINT:")
            sections.append("No explicit Hint: line was found.")
            sections.append("")

        if prior_sql:
            sections.append("PRIOR SQL:")
            sections.append(prior_sql)
            sections.append("")

        if error:
            sections.append("PRIOR SQL EXECUTION ERROR:")
            sections.append(error)
            sections.append("")
            sections.append("Fix the SQL while preserving all hard requirements.")
            sections.append("")

        sections.append("TASK:")
        sections.append(
            "Write one executable SQL query that answers the question "
            "and satisfies all hard requirements."
        )
        sections.append(
            "Return only the SQL query. No explanation, no markdown, no extra text."
        )

        return "\n".join(sections)

    def _call_llm(self, prompt, system):
        try:
            return self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""

    def _extract_sql(self, raw_response) -> str:
        text = self._stringify(raw_response)
        if not text:
            return ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        if sql:
            return str(sql).strip()

        return self._fallback_extract_sql(text)

    def _stringify(self, raw_response) -> str:
        if raw_response is None:
            return ""

        if isinstance(raw_response, str):
            return raw_response

        if isinstance(raw_response, list):
            if not raw_response:
                return ""

            first = raw_response[0]
            if isinstance(first, dict):
                if isinstance(first.get("message"), dict):
                    return str(
                        first["message"].get("content")
                        or first["message"].get("text")
                        or first["message"]
                    )

                return str(
                    first.get("text")
                    or first.get("content")
                    or first.get("sql")
                    or first
                )

            return "\n".join(str(item) for item in raw_response)

        if isinstance(raw_response, dict):
            if isinstance(raw_response.get("message"), dict):
                return str(
                    raw_response["message"].get("content")
                    or raw_response["message"].get("text")
                    or raw_response["message"]
                )

            return str(
                raw_response.get("text")
                or raw_response.get("content")
                or raw_response.get("sql")
                or raw_response
            )

        return str(raw_response)

    def _fallback_extract_sql(self, text: str) -> str:
        cleaned = re.sub(r"