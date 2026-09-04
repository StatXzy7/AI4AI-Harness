"""Parse the 'Hint:' line from the question and enforce its constraints as hard requirements before generating SQL."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2HintGuard(SQLHarness):
    """
    Harness that parses a 'Hint:' line from the natural-language question and
    treats the extracted constraints as HARD requirements that must be reflected
    in the final SQL. The control flow checks compliance by parsing the
    generated SQL, and falls back / re-prompts if any hard constraint is violated.
    """

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        """Solve the text-to-SQL task with hint-aware guard logic."""
        hard_constraints, cleaned_question = self._extract_hint(question)

        # Build a system prompt that frames the hint as non-negotiable.
        system_prompt = self._build_system_prompt(hard_constraints)

        # Build the user prompt (the cleaned question, plus a reminder block).
        user_prompt = self._build_user_prompt(cleaned_question, hard_constraints)

        # Try / verify / retry loop.
        sql = self._generate_with_guard(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            hard_constraints=hard_constraints,
            max_retries=2,
        )

        # Final normalization pass.
        sql = bridge.extract_sql(sql)
        if sql is None:
            sql = ""
        return sql.strip()

    # ------------------------------------------------------------------ #
    # Hint parsing
    # ------------------------------------------------------------------ #
    _HINT_RE = re.compile(
        r"(?P<full>^\s*Hint\s*:\s*(?P<body>.*?))(?=\n\s*\n|\Z)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )

    def _extract_hint(self, question: str) -> Tuple[List[str], str]:
        """
        Pull out the 'Hint: ...' line/block from the question.

        Returns:
            (hard_constraints, cleaned_question)
            - hard_constraints: list of constraint strings parsed from the hint.
            - cleaned_question: the question with the hint block stripped
              (the constraints are still re-injected as an explicit reminder).
        """
        if not question:
            return [], question or ""

        m = self._HINT_RE.search(question)
        if not m:
            return [], question

        hint_body = (m.group("body") or "").strip()
        cleaned = (question[: m.start()] + question[m.end():]).strip()

        hard_constraints = self._parse_constraints(hint_body)
        return hard_constraints, cleaned

    def _parse_constraints(self, hint_body: str) -> List[str]:
        """
        Convert a free-form hint body into a list of hard-constraint strings.

        We split on sentence-ish punctuation so that each atomic claim
        becomes its own guard rail.
        """
        if not hint_body:
            return []

        # Split on '.', ';', or newlines. Keep non-empty fragments.
        raw_parts = re.split(r"[.;\n]+", hint_body)
        constraints = [p.strip(" \t-•*") for p in raw_parts]
        constraints = [c for c in constraints if c]
        return constraints

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #
    def _build_system_prompt(self, hard_constraints: List[str]) -> str:
        base = (
            "You are a precise Text-to-SQL generator. "
            "Only output a single SQL query inside a