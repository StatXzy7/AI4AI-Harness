"""P2P2CKimiS2HintGuard: parse the question's Hint line, restate it as explicit hard requirements before any SQL is written, then generate and guard-repair SQL against those requirements."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2HintGuard(SQLHarness):
    """Hint-first Text-to-SQL harness.

    Control flow (implemented in code, not only in the prompt):
      1. PARSE: extract the 'Hint:' line from the question.
      2. RESTATE: convert the hint into a numbered list of HARD REQUIREMENTS
         (via the LLM, with a deterministic fallback) BEFORE writing SQL.
      3. GENERATE: produce SQL under a prompt that forces a requirement check.
      4. GUARD: verify that hint-derived tokens/literals actually appear in
         the SQL and that it executes; otherwise repair with targeted feedback.
    """

    MAX_REPAIRS = 2
    MAX_VIOLATIONS_REPORTED = 6

    _HINT_LINE_RE = re.compile(r"^\s*hint\s*[:\-]\s*(.+?)\s*$", re.IGNORECASE)
    _HINT_ANY_RE = re.compile(r"hint\s*[:\-]\s*(.+)", re.IGNORECASE | re.DOTALL)

    # ------------------------------------------------------------------ #
    # Entry point                                                         #
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # Step 1 -- parse the Hint line from the question.
        hint = self._parse_hint(question)

        # Step 2 -- restate the hint as hard requirements BEFORE writing SQL.
        requirements = self._restate_requirements(question, hint)

        # Step 3 -- generate SQL constrained by those requirements.
        sql = self._generate_sql(question, hint, requirements)
        if not sql:
            sql = "SELECT 1"

        # Step 4 -- guard loop: hint coverage + executability, else repair.
        for _ in range(self.MAX_REPAIRS):
            violations = self._check_guard(sql, hint)
            result = self.execute(sql)
            if not violations and result.get("ok"):
                return sql
            repaired = self._repair(question, requirements, sql, violations, result)
            if not repaired or repaired.strip() == sql.strip():
                break
            sql = repaired

        return sql

    # ------------------------------------------------------------------ #
    # Step 1: hint parsing                                                #
    # ------------------------------------------------------------------ #
    def _parse_hint(self, question: str) -> str:
        """Extract the Hint line; returns '' when no hint is present."""
        if not question:
            return ""
        for line in question.splitlines():
            m = self._HINT_LINE_RE.match(line)
            if m:
                return m.group(1).strip()
        m = self._HINT_ANY_RE.search(question)
        if m:
            return m.group(1).strip().splitlines()[0].strip()
        return ""

    # ------------------------------------------------------------------ #
    # Step 2: restate hint constraints as hard requirements               #
    # ------------------------------------------------------------------ #
    def _restate_requirements(self, question: str, hint: str) -> str:
        if not hint:
            return ""
        system = (
            "You rewrite vague natural-language hints as precise, enforceable "
            "SQL requirements. You never write SQL yourself."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Hint: {hint}\n\n"
            "Restate the hint as a numbered list of HARD REQUIREMENTS that any "
            "correct SQL query MUST satisfy. For each requirement, be explicit "
            "about the exact table names, column names, comparison operators, "
            "direction of inequalities, string values, and aggregations implied "
            "by the hint. Do NOT write any SQL. Output only the numbered list."
        )
        try:
            text = self._call_llm(prompt, system=system)
            if text and text.strip():
                return text.strip()
        except Exception:
            pass
        # Deterministic fallback: still a hard requirement, stated literally.
        return "1. The query MUST literally satisfy this hint: " + hint

    # ------------------------------------------------------------------ #
    # Step 3: SQL generation under the hard requirements                  #
    # ------------------------------------------------------------------ #
    def _generate_sql(self, question: str, hint: str, requirements: str) -> str:
        req_block = ""
        if requirements:
            req_block = (
                "HARD REQUIREMENTS (MANDATORY -- the query is WRONG unless "
                "EVERY requirement below is satisfied):\n"
                f"{requirements}\n\n"
            )
        system = (
            "You are an expert Text-to-SQL engine. You treat stated hard "
            "requirements as non-negotiable and verify each one before "
            "writing SQL."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"{req_block}"
            "First, briefly restate how each hard requirement will be "
            "enforced in the query (one short line per requirement). "
            "Then output the final SQL query in a single