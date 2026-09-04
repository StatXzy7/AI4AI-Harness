"""Hint-guarded two-stage Text-to-SQL harness: parse the 'Hint:' line, restate it as hard requirements, generate SQL under them, then guard-check and repair before returning."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2HintGuard(SQLHarness):
    """
    P2P2C pipeline: Parse hint -> Plan requirements -> Produce SQL -> Check compliance.

    Stage 1 (Parse):   extract the 'Hint:' line from the question text.
    Stage 2 (Plan):    restate the hint as a numbered list of HARD REQUIREMENTS.
    Stage 3 (Produce): generate SQL with those requirements injected as mandatory
                       constraints in the prompt (control-flow enforced, not just
                       prompt-suggested).
    Stage 4 (Check):   guard the SQL with (a) a deterministic literal-presence check
                       derived from the hint and (b) an LLM compliance review of each
                       requirement; regenerate with violation feedback on failure.
    Stage 5 (Repair):  execute the SQL and regenerate on database errors while still
                       enforcing every hard requirement.
    """

    MAX_GUARD_ATTEMPTS = 2
    MAX_REPAIR_ATTEMPTS = 3
    MAX_EMPTY_ATTEMPTS = 2

    # ---------------- LLM helper ----------------

    def _call_llm(self, prompt: str, system: str = "") -> str:
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            return str(out[0]) if out else ""
        return str(out) if out is not None else ""

    # ---------------- Stage 1: parse the Hint line ----------------

    def _parse_hint(self, question: str) -> str:
        """Extract the text following 'Hint:' (line-based first, inline fallback)."""
        if not question:
            return ""
        for line in question.splitlines():
            m = re.match(r"(?i)^\s*hint\s*[:：]\s*(.+?)\s*$", line)
            if m:
                return m.group(1).strip()
        m = re.search(r"(?is)\bhint\s*[:：]\s*(.+)$", question)
        if m:
            return m.group(1).strip()
        return ""

    def _strip_hint(self, question: str) -> str:
        """Remove the Hint line (or inline Hint suffix) to get the bare NL question."""
        if not question:
            return ""
        kept = [
            ln for ln in question.splitlines()
            if not re.match(r"(?i)^\s*hint\s*[:：]", ln)
        ]
        cleaned = "\n".join(kept)
        cleaned = re.sub(r"(?is)\bhint\s*[:：].*$", "", cleaned).strip()
        return cleaned or question.strip()

    # ---------------- Stage 2: restate hint as hard requirements ----------------

    def _restate_requirements(self, nl_question: str, hint: str) -> list:
        """Use the LLM to convert the hint into a list of enforceable requirements."""
        if not hint:
            return []
        system = (
            "You are a meticulous requirements engineer for a Text-to-SQL system. "
            "You convert informal hints into precise, enforceable SQL requirements."
        )
        prompt = (
            "Question:\n"
            f"{nl_question}\n\n"
            "Hint:\n"
            f"{hint}\n\n"
            "Restate the Hint as a numbered list of HARD REQUIREMENTS that the SQL "
            "query MUST satisfy. Each requirement must be concrete and checkable "
            "(e.g., \"Filter rows where column X = 'Y'\", \"Use table T\", "
            "\"Order by column C descending\", \"Return only column A\"). "
            "Do NOT write SQL. Do NOT add new assumptions beyond the hint. "
            "Output ONLY the numbered list."
        )
        text = self._call_llm(prompt, system=system)
        return self._parse_requirement_list(text)

    def _parse_requirement_list(self, text: str) -> list:
        reqs = []
        for line in (text or "").splitlines():
            s = line.strip()
            if not s:
                continue
            m = re.match(r"^(?:\d+[\.\)]\s*|[-*•]\s+)(.+)$", s)
            if m:
                reqs.append(m.group(1).strip())
            elif reqs and not re.match(r"(?i)^(requirement|output|note)\b", s):
                reqs[-1] += " " + s  # continuation of previous item
        return reqs

    def _requirements_block(self, requirements: list) -> str:
        if not requirements:
            return ""
        lines = ["HARD REQUIREMENTS (the SQL MUST satisfy every one of these):"]
        for i, r in enumerate(requirements, 1):
            lines.append(f"{i}. {r}")
        return "\n".join(lines)

    # ---------------- Stage 3: produce SQL under the requirements ----------------

    def _generate_sql(self, nl_question: str, requirements: list,
                      feedback: str = "", previous_sql: str = "") -> str:
        req_block = self._requirements_block(requirements)
        system = (
            "You are an expert SQLite SQL generator. Output ONLY a single SQL query "
            "inside a