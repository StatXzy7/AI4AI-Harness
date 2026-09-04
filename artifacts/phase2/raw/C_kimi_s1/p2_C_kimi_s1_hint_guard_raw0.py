"""Parse the question's 'Hint:' line and restate its constraints as numbered hard requirements that are enforced before SQL is written and re-asserted throughout a bounded repair loop."""

import re
from typing import List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS1HintGuard(SQLHarness):
    """Hint-guard harness for a frozen weak Text-to-SQL solver.

    Control flow (the strategy lives here, not just in prompt text):
      1. Parse the 'Hint:' line out of the raw question string.
      2. Mechanically split the hint into atomic clauses and restate each
         clause as a numbered, MANDATORY hard requirement.
      3. Build the generation prompt as schema + question + requirements,
         forcing the constraints to be restated *before* any SQL is written.
      4. Extract the SQL, execute it, and on failure run a bounded repair
         loop whose prompts always re-assert the same hard requirements.
    """

    MAX_ATTEMPTS = 3

    # ------------------------------------------------------------- hint parsing
    _HINT_LINE_RE = re.compile(r"(?im)^\s*hint\s*:\s*(?P<hint>.+?)\s*$")
    _HINT_INLINE_RE = re.compile(r"(?is)\bhint\s*:\s*(?P<hint>.+)$")
    _CLAUSE_SPLIT_RE = re.compile(r"(?:;|\.\s+|\s+--\s+|\n+)")

    def _extract_hint(self, question: str) -> str:
        """Return the raw hint text, or '' when the question carries no hint."""
        match = self._HINT_LINE_RE.search(question)
        if not match:
            match = self._HINT_INLINE_RE.search(question)
        return match.group("hint").strip() if match else ""

    def _split_clauses(self, hint: str) -> List[str]:
        """Break the hint into atomic constraint clauses."""
        clauses = []
        for part in self._CLAUSE_SPLIT_RE.split(hint):
            clause = part.strip(" \t.;")
            if clause:
                clauses.append(clause)
        if not clauses and hint.strip():
            clauses = [hint.strip()]
        return clauses

    def _requirements_block(self, hint: str) -> str:
        """Restate hint clauses as numbered, mandatory hard requirements."""
        clauses = self._split_clauses(hint)
        if not clauses:
            return ""
        lines = [
            "HARD REQUIREMENTS (parsed from the hint; every one is MANDATORY "
            "and must be enforced by the SQL you write):"
        ]
        for idx, clause in enumerate(clauses, start=1):
            lines.append(f"  R{idx}. The SQL MUST satisfy: {clause}.")
        lines.append(
            "R1..R{0} are binding constraints, not suggestions; a query that "
            "violates any of them is wrong even if it executes.".format(len(clauses))
        )
        return "\n".join(lines)

    # --------------------------------------------------------------- prompting
    _SYSTEM = (
        "You are a meticulous Text-to-SQL engine. You emit exactly one SQLite "
        "query inside a