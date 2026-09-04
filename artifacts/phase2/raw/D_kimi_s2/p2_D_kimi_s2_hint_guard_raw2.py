"""Parse the Hint line into mandatory MUST requirements before SQL generation and repair once if hint-derived anchors vanish."""
from __future__ import annotations

import re
from typing import List, Sequence

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2HintGuard(SQLHarness):
    _HINT_LINE_RE = re.compile(r"(?im)^\s*hint\s*:\s*(?P<hint>.*?)\s*$")
    _QUOTED_VALUE_RE = re.compile(r"'([^']+)'|\"([^\"]+)\"|`([^`]+)`")
    _NUMERIC_VALUE_RE = re.compile(
        r"\b\d{4}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b|\b\d+(?:\.\d+)?\b"
    )

    def solve(self, question: str) -> str:
        question = question or ""
        hint = self._extract_hint(question)
        clauses = self._split_hint_clauses(hint)
        requirements = self._restate_as_hard_requirements(clauses)
        solver_input = self._replace_hint_with_requirements(question, requirements)

        sql = self._generate_sql(solver_input)

        anchors = self._hint_value_anchors(clauses)
        missing = self._missing_anchors(sql, anchors)
        if missing:
            repaired = self._repair_sql(solver_input, sql, missing)
            if repaired:
                repaired_missing = self._missing_anchors(repaired, anchors)
                if len(repaired_missing) < len(missing):
                    sql = repaired
        return sql or "SELECT 1"

    @classmethod
    def _extract_hint(cls, question: str) -> str:
        match = cls._HINT_LINE_RE.search(question or "")
        return match.group("hint").strip() if match else ""

    @staticmethod
    def _split_hint_clauses(hint: str) -> List[str]:
        hint = re.sub(r"\s+", " ", (hint or "").strip())
        if not hint:
            return []
        parts = re.split(r"\s*(?:;|•|●|◦)\s*|\s+(?=(?:\d+[.)]|[-*])\s)", hint)
        clauses: List[str] = []
        for part in parts:
            part = re.sub(r"^(?:\d+[.)]|[-*•])\s*", "", part).strip()
            if part:
                clauses.append(part)
        return clauses or [hint]

    @staticmethod
    def _restate_as_hard_requirements(clauses: Sequence[str]) -> List[str]:
        requirements: List[str] = []
        imperative_starts = {
            "use", "calculate", "compute", "filter", "return", "show", "list",
            "include", "exclude", "join", "group", "order", "limit", "select",
            "count", "sum", "find", "get", "sort", "rank", "deduplicate",
        }
        constraint_starts = re.compile(
            r"(?i)^(only|exactly|at least|at most|no more than|no less than|"
            r"greater than|less than|equal to|before|after|between|not|without|with)\b"
        )
        for clause in clauses:
            clause = re.sub(r"\s+", " ", clause).strip().rstrip(".")
            if not clause:
                continue
            first = clause.split(None, 1)[0].lower().strip(",:") if clause.split(None, 1) else ""
            if first in imperative_starts:
                requirements.append(f"MUST {clause}.")
            elif constraint_starts.match(clause):
                requirements.append(f"MUST satisfy: {clause}.")
            else:
                requirements.append(f"MUST satisfy this hint constraint: {clause}.")
        return requirements

    @classmethod
    def _replace_hint_with_requirements(cls, question: str, requirements: Sequence[str]) -> str:
        if not requirements:
            return question
        block = (
            "HARD REQUIREMENTS parsed from Hint (mandatory, not optional):\n"
            + "\n".join(f"{i}. {requirement}" for i, requirement in enumerate(requirements, 1))
        )
        if cls._HINT_LINE_RE.search(question):
            return cls._HINT_LINE_RE.sub(block, question, count=1)
        return question.rstrip() + "\n\n" + block

    def _generate_sql(self, solver_input: str) -> str:
        prompt = self._sql_prompt(solver_input)
        response = self.llm(
            prompt,
            system=(
                "You are a careful Text-to-SQL generator. Treat every HARD REQUIREMENT "
                "as a mandatory filter/join/aggregation/ordering/limit and output only SQL."
            ),
            temperature=0.0,
            n=1,
        )
        sql = bridge.extract_sql(self._llm_text(response)).strip()
        if sql:
            return sql

        strict_prompt = prompt + "\nReturn exactly one SQL statement and nothing else."
        strict_response = self.llm(
            strict_prompt,
            system="Output only one valid SQL statement.",
            temperature=0.0,
            n=1,
        )
        return bridge.extract_sql(self._llm_text(strict_response)).strip()

    def _repair_sql(self, solver_input: str, sql: str, missing: Sequence[str]) -> str:
        prompt = (
            f"{self._sql_prompt(solver_input)}\n\n"
            "Previous SQL:\n"
            f"{sql}\n\n"
            "The previous SQL dropped mandatory hint-derived value anchors: "
            f"{', '.join(missing)}. Rewrite the SQL so every HARD REQUIREMENT is satisfied "
            "and those anchors/values are explicitly represented where appropriate. "
            "Return only the corrected SQL."
        )
        response = self.llm(
            prompt,
            system="Repair the SQL. Output only one valid SQL statement.",
            temperature=0.0,
            n=1,
        )
        return bridge.extract_sql(self._llm_text(response)).strip()

    def _sql_prompt(self, solver_input: str) -> str:
        return (
            "Database schema:\n"
            f"{getattr(self, 'schema', '')}\n\n"
            "Task:\n"
            f"{solver_input}\n\n"
            "Write exactly one valid SQL statement that answers the task. Encode every "
            "HARD REQUIREMENT in WHERE/JOIN/GROUP BY/HAVING/ORDER BY/LIMIT as appropriate. "
            "Return only SQL, with no markdown and no explanation."
        )

    @classmethod
    def _hint_value_anchors(cls, clauses: Sequence[str]) -> List[str]:
        anchors = {}
        for clause in clauses:
            for match in cls._QUOTED_VALUE_RE.finditer(clause):
                value = next((group for group in match.groups() if group), "").strip()
                if len(value) >= 2:
                    anchors[value] = None
            for match in cls._NUMERIC_VALUE_RE.finditer(clause):
                anchors[match.group(0)] = None
        return sorted(anchors.keys(), key=len, reverse=True)

    @classmethod
    def _missing_anchors(cls, sql: str, anchors: Sequence[str]) -> List[str]:
        if not anchors:
            return []
        if not sql:
            return list(anchors)
        folded_sql = re.sub(r"\s+", " ", sql).casefold()
        missing: List[str] = []
        for anchor in anchors:
            anchor_text = re.sub(r"\s+", " ", str(anchor)).strip()
            folded_anchor = anchor_text.casefold()
            if not folded_anchor:
                continue
            if re.fullmatch(r"\d+(?:\.\d+)?", folded_anchor):
                present = re.search(
                    rf"(?<![\d.]){re.escape(folded_anchor)}(?![\d.])", folded_sql
                ) is not None
            else:
                present = folded_anchor in folded_sql
            if not present:
                missing.append(anchor_text)
        return missing

    @classmethod
    def _llm_text(cls, response) -> str:
        if response is None:
            return ""
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            for key in ("sql", "text", "content", "answer", "output"):
                value = response.get(key)
                if value:
                    return cls._llm_text(value)
            choices = response.get("choices")
            if choices:
                return cls._llm_text(choices)
        if isinstance(response, (list, tuple)):
            if not response:
                return ""
            first = response[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and message.get("content"):
                    return cls._llm_text(message.get("content"))
                if first.get("text") or first.get("content"):
                    return cls._llm_text(first.get("text") or first.get("content"))
            return cls._llm_text(first)
        return str(response)