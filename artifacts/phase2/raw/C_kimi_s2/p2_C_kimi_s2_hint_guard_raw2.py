"""Hint-Guard harness: parse the 'Hint:' line out of the question, restate its constraints as explicit hard requirements, then generate SQL under those requirements and enforce them through an audit-and-repair control loop."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2HintGuard(SQLHarness):
    """Parse -> Restate -> Constrain -> Guard.

    The 'Hint:' line is extracted from the question in pure control flow,
    restated by the LLM as a numbered list of HARD REQUIREMENTS, injected as
    non-negotiable constraints into SQL generation, and finally enforced by a
    guard loop that audits requirement compliance and executes the query,
    repairing with concrete feedback whenever either check fails.
    """

    MAX_REPAIR_ROUNDS = 2

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # Stage 1 (control flow): parse the 'Hint:' line out of the question.
        hint, body = self._split_hint(question)

        # Stage 2 (LLM, captured as data): restate hint constraints as hard requirements.
        requirements = self._restate_requirements(body, hint)

        # Stage 3 (LLM): generate SQL with the requirements injected as hard constraints.
        sql = self._generate_sql(body, hint, requirements)

        # Stage 4 (control flow): guard the SQL — audit requirement coverage,
        # execute it, and drive bounded repair rounds when either check fails.
        sql = self._guard_sql(body, hint, requirements, sql)

        return sql

    # ------------------------------------------------------------------ #
    # Stage 1: hint parsing (pure control flow)
    # ------------------------------------------------------------------ #
    def _split_hint(self, question: str):
        """Return (hint_text, question_without_hint)."""
        text = question or ""
        match = re.search(r"(?im)^[ \t]*hint[ \t]*:[ \t]*(.*)$", text)
        if not match:
            match = re.search(r"(?is)\bhint[ \t]*:[ \t]*(.+)$", text)
        if match:
            hint = match.group(1).strip()
            body = (text[: match.start()] + "\n" + text[match.end():]).strip()
        else:
            hint, body = "", text.strip()
        return hint, body

    # ------------------------------------------------------------------ #
    # Stage 2: restate the hint as hard requirements
    # ------------------------------------------------------------------ #
    def _restate_requirements(self, body: str, hint: str) -> str:
        if not hint:
            return ("No explicit hint was provided. Derive every constraint "
                    "(filters, columns, aggregations, ordering, limits) directly "
                    "from the question text.")
        system = ("You are a meticulous SQL requirements analyst. You never write "
                  "SQL; you only extract and formalize constraints.")
        prompt = f"""Question:
{body}

Hint:
{hint}

Restate the hint as a numbered list of HARD REQUIREMENTS that any correct SQL query for the question MUST satisfy.
Rules:
- One requirement per line, prefixed with "R<n>:".
- Each requirement must be concrete and checkable in SQL (name exact tables/columns/values the hint mentions).
- Translate vague wording into explicit SQL obligations (e.g. "exclude X" -> "the WHERE clause must filter out X"; "use column Y" -> "the query must reference column Y").
- Do NOT write any SQL query. Do NOT add explanations beyond the numbered list."""
        text = self._llm_text(prompt, system=system)
        if not text:
            text = "R1: Faithfully apply this hint when writing the SQL: " + hint
        return text

    # ------------------------------------------------------------------ #
    # Stage 3: constrained SQL generation
    # ------------------------------------------------------------------ #
    def _generate_sql(self, body: str, hint: str, requirements: str,
                      feedback: str = "") -> str:
        system = ("You are an expert SQLite query writer. You treat stated "
                  "requirements as non-negotiable hard constraints.")
        hint_block = f"\nOriginal hint (for context):\n{hint}\n" if hint else ""
        feedback_block = ""
        if feedback:
            feedback_block = f"""
The previous attempt was REJECTED for this reason:
{feedback}
Produce a corrected query that fixes the rejection AND still satisfies every hard requirement.
"""
        prompt = f"""Database schema:
{self.schema}

Question:
{body}
{hint_block}
HARD REQUIREMENTS (the query MUST satisfy every one of them):
{requirements}
{feedback_block}
Write a single SQLite query that answers the question while violating none of the hard requirements.
Output only the SQL query."""
        raw = self._llm_text(prompt, system=system)
        return bridge.extract_sql(raw).strip()

    # ------------------------------------------------------------------ #
    # Stage 4: guard + bounded repair loop (control flow)
    # ------------------------------------------------------------------ #
    def _guard_sql(self, body: str, hint: str, requirements: str, sql: str) -> str:
        last_issue = ""
        for _ in range(self.MAX_REPAIR_ROUNDS + 1):
            if not sql:
                sql = self._generate_sql(
                    body, hint, requirements,
                    feedback=last_issue or "Previous output contained no extractable SQL.")
                if not sql:
                    continue

            # 4a. Requirement-compliance audit: LLM verdict, parsed in control flow.
            ok, reason = self._audit_requirements(sql, requirements)
            if ok:
                # 4b. Hard gate: the query must actually execute.
                result = self.execute(sql)
                if result.get("ok"):
                    return sql
                last_issue = ("The query failed to execute. SQLite error: "
                              + str(result.get("error", "unknown error")))
            else:
                last_issue = reason

            repaired = self._generate_sql(body, hint, requirements, feedback=last_issue)
            if repaired:
                sql = repaired

        # Exhausted repairs: return the best (most recently repaired) SQL we have.
        return sql

    def _audit_requirements(self, sql: str, requirements: str):
        """Return (passed, rejection_reason). Unparsable verdicts defer to the execution gate."""
        system = "You are a strict SQL compliance auditor. Answer with the verdict first."
        prompt = f"""SQL query under audit:
{sql}

HARD REQUIREMENTS:
{requirements}

Does the SQL query satisfy EVERY hard requirement above?
Reply in exactly this format:
VERDICT: YES
or
VERDICT: NO
REASON: <the single most important violated requirement and why>"""
        out = self._llm_text(prompt, system=system)
        verdict = re.search(r"(?i)verdict\s*:\s*(yes|no)\b", out)
        if not verdict:
            return True, ""  # auditor gave no usable verdict; let execution decide
        if verdict.group(1).lower() == "yes":
            return True, ""
        reason = ""
        m = re.search(r"(?i)reason\s*:\s*(.+)", out, re.S)
        if m:
            reason = m.group(1).strip()
        return False, "Requirement violation reported by auditor: " + (reason or "unspecified")

    # ------------------------------------------------------------------ #
    # LLM helper — normalizes str vs. list return values
    # ------------------------------------------------------------------ #
    def _llm_text(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            return str(out[0]).strip() if out else ""
        return str(out).strip()