"""Hint-guard harness: parses the question's 'Hint:' line, restates it as numbered HARD REQUIREMENTS, then drafts SQL and runs a bounded guard loop that audits the SQL against those requirements (plus execution) and repairs it on any violation."""

from __future__ import annotations

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2HintGuard(SQLHarness):
    """Hint-Guard Text-to-SQL harness.

    The strategy lives in the control flow, not only in prompts:
      1. PARSE   -- regex-extract the 'Hint:' line from the raw question.
      2. RESTATE -- a dedicated LLM call rewrites the hint as a numbered list
                    of independently checkable HARD REQUIREMENTS.
      3. DRAFT   -- the SQL writer is conditioned on those requirements.
      4. GUARD   -- a bounded loop that (a) audits the draft against every
                    requirement with a strict auditor call plus a literal-value
                    heuristic, and (b) executes the SQL; any violation or
                    execution error triggers a repair call, and the repaired
                    SQL is re-checked from the top.
    """

    MAX_REPAIR_ROUNDS = 3

    _HINT_RE = re.compile(
        r"^\s*hint\s*[:\-]\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE
    )
    _VERDICT_RE = re.compile(r"verdict\s*[:\-]\s*(pass|fail)", re.IGNORECASE)
    _REQ_LINE_RE = re.compile(
        r"req(?:uirement)?\s*(\d+)\s*[:\-]\s*(pass|fail)\b\s*[:\-]?\s*(.*)",
        re.IGNORECASE,
    )
    _QUOTED_RE = re.compile(r"[\"']([^\"']{2,})[\"']")

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        # Stage 1: parse the Hint line out of the question (pure control flow).
        hint = self._parse_hint(question)

        # Stage 2: restate the hint constraints as hard requirements.
        requirements = self._restate_requirements(question, hint)

        # Stage 3: draft SQL conditioned on the hard requirements.
        sql = self._draft_sql(question, hint, requirements)

        # Stage 4: guard loop -- audit requirements, execute, repair.
        sql = self._guard_sql(question, hint, requirements, sql)

        return sql if sql.strip() else "SELECT 1"

    # ------------------------------------------------------- stage 1: parse

    def _parse_hint(self, question: str) -> str:
        """Extract the text following the 'Hint:' marker, or '' if absent."""
        m = self._HINT_RE.search(question or "")
        if not m:
            return ""
        hint = m.group(1).strip()
        if len(hint) >= 2 and hint[0] in "\"'" and hint[-1] == hint[0]:
            hint = hint[1:-1].strip()
        return hint

    # ---------------------------------------------------- stage 2: restate

    def _restate_requirements(self, question: str, hint: str) -> list[str]:
        """Turn the raw hint into a numbered list of hard requirements."""
        if not hint:
            return []
        system = (
            "You are a precise constraint analyst for Text-to-SQL. Your job is "
            "to turn loose hints into unambiguous, checkable hard requirements."
        )
        prompt = f"""Database schema:
{self.schema}

Question:
{question}

Hint line:
{hint}

Task: Restate the hint as a numbered list of HARD REQUIREMENTS that any correct SQL query MUST satisfy.
- One requirement per line, each independently checkable against a candidate SQL query.
- Preserve every literal value, column/table name, comparison direction, and aggregation mentioned in the hint.
- Do not invent requirements that are not implied by the hint or the question.
- Output ONLY the numbered list, e.g.:
1. ...
2. ..."""
        text = self._ask(prompt, system=system, temperature=0.0)
        requirements: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            m = re.match(r"^(?:\d+[.\)]\s*|[-*]\s*)(.+)$", line)
            if m:
                requirements.append(m.group(1).strip())
        if not requirements:
            # Fallback: the raw hint itself becomes the single hard requirement.
            requirements = [hint]
        return requirements

    # ------------------------------------------------------ stage 3: draft

    def _draft_sql(self, question: str, hint: str, requirements: list[str]) -> str:
        system = (
            "You are an expert SQLite query writer. You treat every HARD "
            "REQUIREMENT as non-negotiable and double-check your SQL against "
            "each one before answering."
        )
        prompt = f"""Database schema:
{self.schema}

Question:
{question}

Original hint:
{hint or "(none)"}

HARD REQUIREMENTS (each MUST be satisfied by your SQL):
{self._format_requirements(requirements)}

Think step by step about how each hard requirement maps onto the schema, then write a single SQLite SELECT query.
Return ONLY the SQL query, optionally inside a