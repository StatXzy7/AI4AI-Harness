"""Parse an explicit Hint: line from the question and enforce it as a hard guard before/after generating SQL with the frozen solver."""
from __future__ import annotations

import re
from typing import Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0HintGuard(SQLHarness):
    """Harness that extracts an explicit `Hint:` line from the natural-language
    question and uses it both as a prompting anchor AND as a post-generation
    hard guard: if the produced SQL violates the hint's constraints, the
    harness rewrites the prompt or rejects/repairs the SQL until the
    constraint is satisfied, then returns the final SQL string.
    """

    # Regex to capture the Hint segment. Supports "Hint:", "Hint -",
    # "HINT:", and tolerates surrounding whitespace/newlines.
    _HINT_RE = re.compile(
        r"(?im)^\s*hint\s*[:\-]\s*(?P<hint>.+?)\s*(?:\n\s*\n|\Z)"
    )

    # Common SQL clauses we look for when validating hints
    _AGGREGATES = ("count(", "sum(", "avg(", "min(", "max(", "group by", "having")
    _LIMIT_RE = re.compile(r"(?i)\blimit\s+(\d+|\?)\b")
    _ORDER_RE = re.compile(r"(?i)\border\s+by\s+([a-zA-Z_][\w\."]*)(\s+(?:asc|desc))?")
    _WHERE_RE = re.compile(r"(?i)\bwhere\b")
    _DISTINCT_RE = re.compile(r"(?i)\bselect\s+distinct\b")
    _JOIN_RE = re.compile(r"(?i)\bjoin\b")
    _CTE_RE = re.compile(r"(?i)\bwith\s+[a-zA-Z_]\w*\s+as\b")

    def solve(self, question: str) -> str:
        question = question or ""
        hint = self._extract_hint(question)
        clean_question = self._strip_hint(question)

        # 1) First attempt: ask the frozen solver with the hint injected
        #    as an explicit, capitalized hard-requirement block.
        prompt = self._build_prompt(clean_question, hint)
        sql = self._generate_and_extract(prompt)

        # 2) Validate the generated SQL against the parsed hint.
        #    If it violates a constraint we detected, do up to 2 repair
        #    passes by re-prompting with an explicit violation note.
        if hint:
            for attempt in range(3):
                ok, reason = self._check_hint(sql, hint)
                if ok:
                    break
                repair_prompt = self._build_repair_prompt(
                    clean_question, hint, sql, reason
                )
                sql = self._generate_and_extract(repair_prompt)
            # Final hard guard: if still violating, fall back to a
            # minimal conservative SQL derived from the hint only
            # (better a safe miss than a confidently wrong answer).
            ok, reason = self._check_hint(sql, hint)
            if not ok:
                sql = self._fallback_from_hint(hint, clean_question) or sql

        return sql.strip()

    # ------------------------------------------------------------------ #
    # Hint extraction                                                    #
    # ------------------------------------------------------------------ #
    def _extract_hint(self, question: str) -> Optional[str]:
        m = self._HINT_RE.search(question)
        if not m:
            return None
        hint = m.group("hint").strip()
        return hint or None

    def _strip_hint(self, question: str) -> str:
        return self._HINT_RE.sub("", question).strip()

    # ------------------------------------------------------------------ #
    # Prompt construction                                                 #
    # ------------------------------------------------------------------ #
    def _build_prompt(self, question: str, hint: Optional[str]) -> str:
        if hint:
            return (
                "You are a Text-to-SQL generator. The user's question "
                "includes an explicit HINT. The hint is a HARD REQUIREMENT "
                "that MUST be reflected in the SQL. Treat it as a constraint, "
                "not a suggestion.\n\n"
                f"QUESTION:\n{question}\n\n"
                f"HARD REQUIREMENT (from Hint):\n{hint}\n\n"
                "Return ONLY the SQL statement, no prose."
            )
        return (
            "You are a Text-to-SQL generator. "
            f"QUESTION:\n{question}\n\n"
            "Return ONLY the SQL statement, no prose."
        )

    def _build_repair_prompt(
        self, question: str, hint: str, bad_sql: str, reason: str
    ) -> str:
        return (
            "Your previous SQL violated the following HARD REQUIREMENT.\n\n"
            f"HARD REQUIREMENT:\n{hint}\n\n"
            f"VIOLATION:\n{reason}\n\n"
            f"QUESTION:\n{question}\n\n"
            f"PREVIOUS SQL (rejected):\n{bad_sql}\n\n"
            "Rewrite the SQL so that the hard requirement is satisfied. "
            "Return ONLY the corrected SQL, no prose."
        )

    # ------------------------------------------------------------------ #
    # Generation + extraction                                             #
    # ------------------------------------------------------------------ #
    def _generate_and_extract(self, prompt: str) -> str:
        raw = self.llm(prompt, system="", temperature=0.0, n=1)
        sql = bridge.extract_sql(raw) or raw
        # Clean up code fences if any survived extraction.
        sql = re.sub(r"^