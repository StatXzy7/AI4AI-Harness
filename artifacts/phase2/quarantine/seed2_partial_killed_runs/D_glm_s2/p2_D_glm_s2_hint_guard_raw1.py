"""Parse the question's 'Hint:' line, restate each of its constraints as a numbered hard requirement injected before SQL generation, and guard the emitted query with a compliance audit plus execution-feedback retries."""

import re

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2HintGuard"]


class P2P2DGlmS2HintGuard(SQLHarness):
    """Hint-guarded wrapper around a frozen weak text-to-SQL solver.

    Control flow (the strategy lives here, not just in the prompt):
      1. `_extract_hint` pulls the 'Hint:' line out of the question.
      2. `_hint_to_requirements` splits it into atomic constraints, which are
         restated as numbered HARD REQUIREMENTS by `_format_requirements` and
         placed in the prompt *before* the SQL-writing instruction; the model
         must also restate each requirement before it writes any SQL.
      3. Candidates are generated, validated by execution, and retried with
         the execution error fed back while the hard requirements are
         restated on every attempt.
      4. `_guard_audit` checks an executable candidate against every
         requirement and swaps in a correction only if it also executes.
    """

    MAX_SQL_ATTEMPTS = 3

    _HINT_SCAN_RE = re.compile(r"\bhints?[ \t]*[:\uff1a][ \t]*(.+)$", re.IGNORECASE)

    # --------------------------------------------------------------- public

    def solve(self, question: str) -> str:
        question = question or ""

        # Step 1: parse the Hint line out of the question.
        hint_text = self._extract_hint(question)
        # Step 2: restate its constraints as atomic hard requirements.
        requirements = self._hint_to_requirements(hint_text)

        system = (
            "You are a precise text-to-SQL engine. Translate the question into "
            "exactly one SQL query. Every HARD REQUIREMENT listed in the prompt "
            "is a non-negotiable constraint on the query and its result. "
            "Respond with a single