"""HintGuard harness: parse the question's 'Hint:' line, restate each of its constraints as a numbered hard requirement, generate SQL under those requirements, and guard the result with execution-driven repair."""

import re
from typing import List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2HintGuard(SQLHarness):
    """Text-to-SQL harness that turns the question's Hint line into explicit
    hard requirements enforced during generation and execution-based repair."""

    MAX_REPAIR_ROUNDS = 2

    _HINT_PATTERN = re.compile(r"hint\s*:\s*(.+)", re.IGNORECASE)
    _CLAUSE_SPLIT = re.compile(r";+|(?<=[.])\s+|\n+")

    # ---------------- public entry point ----------------

    def solve(self, question: str) -> str:
        # Step 1: parse the 'Hint:' line out of the question.
        hint = self._parse_hint(question)

        # Step 2: restate the hint's constraints as atomic hard requirements.
        requirements = self._restate_requirements(hint)

        # Step 3: generate SQL under those hard requirements.
        system = (
            "You are an expert Text-to-SQL translator. Translate the "
            "natural-language question into one correct SQL query for the "
            "given schema. Every HARD REQUIREMENT listed in the user message "
            "is mandatory: the query MUST satisfy all of them."
        )
        prompt = self._build_generation_prompt(question, requirements)
        sql = bridge.extract_sql(self._call_llm(prompt, system)).strip()
        if not sql:
            sql = "SELECT 1"

        # Step 4: guard the SQL by executing it and repairing on failure.
        return self._guard_with_execution(question, requirements, sql, system)

    # ---------------- hint parsing & restatement ----------------

    def _parse_hint(self, question: str) -> str:
        """Extract the text following the 'Hint:' marker, if present."""
        match = self._HINT_PATTERN.search(question or "")
        if not match:
            return ""
        return match.group(1).strip()

    def _restate_requirements(self, hint: str) -> List[str]:
        """Split the hint into atomic clauses, each becoming a hard requirement."""
        if not hint:
            return []
        requirements: List[str] = []
        for clause in self._CLAUSE_SPLIT.split(hint):
            clause = clause.strip(" \t\r\n.;")
            if clause:
                requirements.append(clause)
        if not requirements:
            requirements.append(hint)
        return requirements

    def _format_requirements(self, requirements: List[str]) -> str:
        if not requirements:
            return (
                "HARD REQUIREMENTS:\n"
                "(No hint was provided; rely only on the question and schema.)"
            )
        lines = [
            "HARD REQUIREMENTS (derived from the hint; the SQL MUST satisfy every one):"
        ]
        for i, req in enumerate(requirements, 1):
            lines.append(f"{i}. MUST: {req}")
        return "\n".join(lines)

    # ---------------- prompt construction ----------------

    def _build_generation_prompt(self, question: str, requirements: List[str]) -> str:
        parts = [
            "DATABASE SCHEMA:",
            self.schema,
            "",
            "QUESTION:",
            question,
            "",
            self._format_requirements(requirements),
            "",
            "INSTRUCTIONS:",
            "1. Read the QUESTION and every HARD REQUIREMENT above.",
            "2. Write a single SQL query that answers the question while "
            "satisfying ALL hard requirements.",
            "3. Output ONLY the SQL query inside a