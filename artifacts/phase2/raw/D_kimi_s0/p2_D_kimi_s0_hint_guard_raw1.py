"""Harness that parses the question's 'Hint:' line, restates each parsed constraint as a numbered HARD REQUIREMENT when prompting the frozen solver, and then programmatically guards (and repairs) the generated SQL so every hint-derived literal is honored before returning it."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS0HintGuard(SQLHarness):
    """Parse 'Hint:' -> restate as hard requirements -> generate -> guard -> repair.

    The mechanism lives in the control flow, not just the prompt:
      1. _split_hint() extracts the raw 'Hint:' text out of the question.
      2. _atomic_constraints() breaks the hint into individual constraint clauses.
      3. The prompt enumerates them as numbered HARD REQUIREMENTS that override
         the model's own assumptions.
      4. _guard() checks the emitted SQL for the concrete literals (quoted values
         and numbers) each requirement demands.
      5. On violation (or execution failure) a targeted repair pass is issued
         with explicit feedback, up to MAX_REPAIRS times.
    """

    HINT_RE = re.compile(r"hint\s*[:：-]\s*", re.IGNORECASE)
    QUOTED_RE = re.compile(r"'([^']+)'|\"([^\"]+)\"|`([^`]+)`")
    NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
    SPLIT_RE = re.compile(r"(?:\r?\n+|;\s*|\.\s+)")
    MAX_REPAIRS = 2

    # ------------------------------------------------------------------ API
    def solve(self, question: str) -> str:
        clean_question, hint = self._split_hint(question)
        constraints = self._atomic_constraints(hint)
        requirements = self._format_requirements(constraints)

        system = (
            "You are an expert SQLite text-to-SQL generator. "
            "Every HARD REQUIREMENT in the user message is mandatory: it was "
            "parsed from the user's hint and overrides your own assumptions. "
            "Each required value, filter, ordering, and column must be reflected "
            "literally in the SQL. Reply with only the SQL query."
        )

        sql = self._generate(clean_question, requirements, system)

        for _ in range(self.MAX_REPAIRS):
            violations = self._guard(sql, constraints)
            exec_error = None
            if not violations:
                report = self.execute(sql)
                if report.get("ok"):
                    return sql
                exec_error = report.get("error") or "unknown execution error"
            feedback = self._feedback(violations, exec_error)
            sql = self._repair(clean_question, requirements, system, sql, feedback)

        # Best-effort fallback: return the last candidate even if still imperfect.
        return sql

    # ------------------------------------------------------- hint parsing
    def _split_hint(self, question):
        """Split 'question text ... Hint: ...' into (clean_question, hint)."""
        match = self.HINT_RE.search(question)
        if not match:
            return question.strip(), ""
        clean = question[: match.start()].strip()
        hint = question[match.end():].strip()
        return clean, hint

    def _atomic_constraints(self, hint):
        """Break the hint into atomic constraint clauses."""
        if not hint:
            return []
        constraints = []
        for piece in self.SPLIT_RE.split(hint):
            clause = piece.strip(" \t-•*. ")
            if clause:
                constraints.append(clause)
        return constraints

    @staticmethod
    def _format_requirements(constraints):
        """Restate each hint clause as a numbered hard requirement."""
        if not constraints:
            return "(no hint constraints were provided)"
        return "\n".join(
            f"HARD REQUIREMENT {i}: {clause}"
            for i, clause in enumerate(constraints, 1)
        )

    # ------------------------------------------------------------- guard
    def _guard(self, sql, constraints):
        """Return [(constraint, missing_literal), ...] for hint literals absent from the SQL."""
        sql_lower = sql.lower()
        violations = []
        for constraint in constraints:
            for literal in self._literals(constraint):
                if literal.lower() not in sql_lower:
                    violations.append((constraint, literal))
        return violations

    def _literals(self, text):
        """Extract checkable literals (quoted/backticked values, numbers) from a constraint."""
        found = []
        for m in self.QUOTED_RE.finditer(text):
            found.append(next(g for g in m.groups() if g))
        found.extend(self.NUMBER_RE.findall(text))
        seen, ordered = set(), []
        for lit in found:
            key = lit.lower()
            if key and key not in seen:
                seen.add(key)
                ordered.append(lit)
        return ordered

    @staticmethod
    def _feedback(violations, exec_error):
        lines = [
            f"- Missing required value '{literal}' demanded by hint constraint "
            f"{constraint!r}; this HARD REQUIREMENT must appear in the SQL."
            for constraint, literal in violations
        ]
        if exec_error:
            lines.append(f"- The SQL failed to execute: {exec_error}")
        return "\n".join(lines)

    # ---------------------------------------------------------- llm calls
    def _generate(self, question, requirements, system):
        prompt = (
            "=== DATABASE SCHEMA ===\n"
            f"{self.schema}\n\n"
            "=== QUESTION ===\n"
            f"{question}\n\n"
            "=== HARD REQUIREMENTS (parsed from the hint; ALL are mandatory) ===\n"
            f"{requirements}\n\n"
            "Write ONE SQLite query that answers the QUESTION while satisfying "
            "EVERY hard requirement above with its exact values, filters, "
            "ordering, and columns. Output only the SQL."
        )
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        return self._to_sql(raw)

    def _repair(self, question, requirements, system, bad_sql, feedback):
        prompt = (
            "Your previous SQL was REJECTED by the hint guard.\n\n"
            "=== PREVIOUS SQL ===\n"
            f"{bad_sql}\n\n"
            "=== WHY IT WAS REJECTED ===\n"
            f"{feedback}\n\n"
            "=== HARD REQUIREMENTS (ALL mandatory; parsed from the hint) ===\n"
            f"{requirements}\n\n"
            "=== QUESTION ===\n"
            f"{question}\n\n"
            "=== DATABASE SCHEMA ===\n"
            f"{self.schema}\n\n"
            "Rewrite the FULL corrected SQLite query: fix every listed issue "
            "while keeping all hard requirements satisfied. Do not drop any "
            "required literal, filter, or ordering. Output only the corrected SQL."
        )
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)
        return self._to_sql(raw)

    @staticmethod
    def _to_sql(raw):
        sql = bridge.extract_sql(raw)
        if not sql:
            sql = raw if isinstance(raw, str) else str(raw)
        return sql.strip()