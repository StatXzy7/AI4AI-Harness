"""Harness that parses the 'Hint:' line from the question, restates its constraints as hard MUST-requirements in the control flow before any SQL is written, drafts SQL conditioned on them, and guards the result with a requirement-compliance check plus live execution inside a bounded repair loop."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS0HintGuard(SQLHarness):
    """Parse the question's 'Hint:' line, restate it as hard requirements,
    generate SQL only after those requirements are in place, then guard the
    candidate via an LLM compliance check and real execution, repairing until
    both pass (bounded attempts)."""

    MAX_REPAIR_ATTEMPTS = 3

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def solve(self, question: str) -> str:
        # Step 1: Parse the 'Hint:' line out of the question (control flow,
        # not prompt).
        hint = self._parse_hint(question)

        # Step 2: Restate the hint's constraints as HARD REQUIREMENTS before
        # any SQL is generated.
        requirements = self._restate_requirements(question, hint)

        # Step 3: Draft SQL explicitly conditioned on the hard requirements.
        sql = self._draft_sql(question, requirements)

        # Step 4: Guard — verify requirement compliance and executability,
        # repairing within a bounded loop.
        sql = self._guard_and_repair(question, requirements, sql)

        return sql or ""

    # ------------------------------------------------------------------
    # Step 1: hint parsing
    # ------------------------------------------------------------------
    def _parse_hint(self, question: str) -> str:
        """Extract the text following the 'Hint:' marker, if present."""
        match = re.search(r"hint\s*:\s*", question, flags=re.IGNORECASE)
        if not match:
            return ""
        tail = question[match.end():]
        # The hint block ends at a blank line if one exists.
        tail = tail.split("\n\n")[0]
        # Flatten any continuation lines into one line of text.
        return " ".join(
            line.strip() for line in tail.splitlines() if line.strip()
        ).strip()

    # ------------------------------------------------------------------
    # Step 2: restate hint as hard requirements
    # ------------------------------------------------------------------
    def _restate_requirements(self, question: str, hint: str) -> list:
        """Convert the hint into explicit MUST-style hard requirements.

        Uses the LLM first; falls back to a deterministic sentence-splitting
        restatement so the control flow always yields requirements when a
        hint exists.
        """
        if not hint:
            return []

        system = (
            "You convert Text-to-SQL hints into a checklist of hard "
            "requirements for the SQL query."
        )
        prompt = (
            "Database schema:\n" + self.schema + "\n\n"
            "Question:\n" + question + "\n\n"
            "Hint:\n" + hint + "\n\n"
            "Restate every constraint, rule, mapping, or clue contained in "
            "the Hint as explicit HARD REQUIREMENTS that the SQL query MUST "
            "satisfy. Resolve any table/column references against the schema "
            "above and use exact schema names. Output one requirement per "
            "line, each starting with the word 'MUST'. No explanations, no "
            "SQL, no markdown."
        )
        text = self._call_llm(prompt, system=system)

        requirements = []
        for raw in text.splitlines():
            line = raw.strip().lstrip("-*•").strip()
            line = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
            if not line:
                continue
            if not line.upper().startswith("MUST"):
                line = "MUST " + line[0].upper() + line[1:]
            requirements.append(line)

        if not requirements:
            # Deterministic fallback: each hint sentence becomes a MUST.
            for sentence in re.split(r"(?<=[.;])\s+", hint):
                sentence = sentence.strip()
                if sentence:
                    requirements.append(
                        "MUST " + sentence[0].upper() + sentence[1:]
                    )
        return requirements

    def _requirements_block(self, requirements: list) -> str:
        if not requirements:
            return "(No hint was provided; follow the question text exactly.)"
        return "\n".join(
            f"{i + 1}. {req}" for i, req in enumerate(requirements)
        )

    # ------------------------------------------------------------------
    # Step 3: draft SQL under the hard requirements
    # ------------------------------------------------------------------
    def _draft_sql(self, question: str, requirements: list) -> str:
        system = (
            "You are an expert SQLite SQL generator. Produce exactly one "
            "valid SQLite query. Output SQL only, no markdown, no commentary."
        )
        prompt = (
            "Database schema:\n" + self.schema + "\n\n"
            "Question:\n" + question + "\n\n"
            "HARD REQUIREMENTS (the query MUST satisfy ALL of these; they "
            "override any conflicting intuition):\n"
            + self._requirements_block(requirements) + "\n\n"
            "Write one SQLite SELECT query that answers the Question and "
            "satisfies every HARD REQUIREMENT above. Return only the SQL."
        )
        text = self._call_llm(prompt, system=system)
        return bridge.extract_sql(text)

    # ------------------------------------------------------------------
    # Step 4: guard and repair
    # ------------------------------------------------------------------
    def _guard_and_repair(
        self, question: str, requirements: list, sql: str
    ) -> str:
        """Check compliance + execution; repair until clean or attempts run
        out. Prefers a query that both executes and satisfies all
        requirements; otherwise falls back to any executable query, else the
        last attempt."""
        last_executable = ""
        for _ in range(self.MAX_REPAIR_ATTEMPTS + 1):
            result = self.execute(sql) if sql else {"ok": False, "error": "empty SQL"}
            ok = bool(result.get("ok"))
            if ok:
                last_executable = sql

            violations = self._check_requirements(question, requirements, sql)

            if ok and not violations:
                return sql

            exec_error = "" if ok else str(result.get("error", "unknown error"))
            sql = self._repair_sql(
                question, requirements, sql, violations, exec_error
            )
            if not sql:
                break

        return last_executable if last_executable else sql

    def _check_requirements(
        self, question: str, requirements: list, sql: str
    ) -> list:
        """LLM guard: return the list of violated hard requirements ([] if
        all hold or there is nothing to check)."""
        if not requirements or not sql:
            return []
        system = (
            "You are a strict SQL compliance checker. You only flag clear "
            "violations."
        )
        prompt = (
            "Database schema:\n" + self.schema + "\n\n"
            "Question:\n" + question + "\n\n"
            "HARD REQUIREMENTS:\n"
            + self._requirements_block(requirements) + "\n\n"
            "Candidate SQL:\n" + sql + "\n\n"
            "For EACH numbered requirement, decide whether the Candidate SQL "
            "satisfies it. List ONLY the numbers of the VIOLATED "
            "requirements, one per line, each followed by a one-sentence "
            "reason. If every requirement is satisfied, output exactly:\n"
            "ALL SATISFIED"
        )
        text = self._call_llm(prompt, system=system).strip()
        if not text or "ALL SATISFIED" in text.upper():
            return []
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _repair_sql(
        self,
        question: str,
        requirements: list,
        sql: str,
        violations: list,
        exec_error: str,
    ) -> str:
        problems = []
        if violations:
            problems.append(
                "Violated HARD REQUIREMENTS:\n"
                + "\n".join("- " + v for v in violations)
            )
        if exec_error:
            problems.append("Execution error:\n" + exec_error)
        problem_block = (
            "\n\n".join(problems) if problems else "The query is incorrect."
        )

        system = (
            "You are an expert SQLite SQL fixer. Produce exactly one "
            "corrected SQLite query. Output SQL only, no markdown."
        )
        prompt = (
            "Database schema:\n" + self.schema + "\n\n"
            "Question:\n" + question + "\n\n"
            "HARD REQUIREMENTS (ALL must hold):\n"
            + self._requirements_block(requirements) + "\n\n"
            "Current SQL:\n" + (sql or "(none)") + "\n\n"
            + problem_block + "\n\n"
            "Rewrite the SQL so that it executes without error AND satisfies "
            "every HARD REQUIREMENT. Return only the corrected SQL."
        )
        text = self._call_llm(prompt, system=system)
        fixed = bridge.extract_sql(text)
        return fixed or sql

    # ------------------------------------------------------------------
    # LLM helper
    # ------------------------------------------------------------------
    def _call_llm(self, prompt: str, system: str = "") -> str:
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            return str(out[0]) if out else ""
        return str(out) if out is not None else ""