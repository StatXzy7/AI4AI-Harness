"""Harness that parses the 'Hint:' line from the question, restates it as hard requirements in the prompt, and enforces those requirements in the control flow by rejecting/repairing candidate SQL that omits required hint elements or fails execution."""

import re
from typing import List, Optional

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2HintGuard(SQLHarness):
    """Hint-Guard Text-to-SQL harness.

    Control-flow strategy:
      1. Parse the 'Hint:' line out of the raw question string.
      2. Split the hint into individual constraint clauses and restate them
         verbatim as a numbered HARD REQUIREMENTS block placed *before* the
         SQL-writing instruction in the prompt.
      3. Derive a concrete token checklist from the hint (quoted literals,
         numbers, backticked names, and schema identifiers mentioned in the
         hint).
      4. Generate SQL, then GUARD it in code: any candidate missing a
         required token, or failing execution, is rejected and regenerated
         with explicit feedback until compliant or attempts are exhausted.
    """

    MAX_ATTEMPTS: int = 3
    MAX_REQUIRED_TOKENS: int = 10

    _HINT_LINE_RE = re.compile(r"(?im)^\s*hint\s*:\s*(.+?)\s*$")
    _HINT_INLINE_RE = re.compile(r"(?is)\bhint\s*:\s*(.+)")
    _QUOTED_RE = re.compile(r"'([^']+)'|\"([^\"]+)\"|`([^`]+)`")
    _NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")
    _IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

    _STOPWORDS = frozenset({
        "the", "a", "an", "of", "and", "or", "by", "to", "in", "on", "for",
        "with", "is", "are", "was", "were", "that", "this", "these", "those",
        "hint", "sql", "query", "select", "from", "where", "group", "order",
        "limit", "as", "how", "what", "which", "many", "much", "list", "show",
        "find", "give", "name", "number", "total",
    })

    # ------------------------------------------------------------------ #
    # Main entry point                                                    #
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        hint_text = self._extract_hint(question)
        constraints = self._split_constraints(hint_text)
        required_tokens = self._requirement_tokens(hint_text)
        requirement_block = self._format_requirements(constraints)

        feedback = ""
        last_sql = ""
        executable_sql = ""

        for _ in range(self.MAX_ATTEMPTS):
            prompt = self._build_prompt(question, requirement_block, feedback)
            raw = self.llm(
                prompt,
                system=self._system_prompt(),
                temperature=0.0,
                n=1,
            )
            if isinstance(raw, (list, tuple)):
                raw = raw[0] if raw else ""
            sql = bridge.extract_sql(raw or "")

            if not sql:
                feedback = (
                    "Your previous reply contained no extractable SQL. "
                    "Return exactly one SQL query inside a single