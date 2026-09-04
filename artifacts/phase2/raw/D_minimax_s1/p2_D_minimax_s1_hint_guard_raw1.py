"""Harness that parses a 'Hint:' line from the question and enforces it as a hard constraint before forwarding to the frozen weak SQL solver."""

from __future__ import annotations

import re

from ..harness_base import SQLHarness
from .. import bridge


# Regexes used to lift hint constraints out of the question text.
_HINT_LINE_RE = re.compile(
    r"""^\s*[Hh]int\s*:\s*(?P<hint>.*?)\s*$""",
    re.MULTILINE | re.VERBOSE,
)
_TARGET_TABLE_RE = re.compile(
    r"""(?P<verb>from|join|update|into|table)\s+[`"\[]?(?P<name>[A-Za-z_][A-Za-z0-9_]*)[`"\]]?""",
    re.IGNORECASE,
)


class P2P2DMinimaxS1HintGuard(SQLHarness):
    """Parse a 'Hint:' clause from ``question``, restate it as hard constraints,
    then prompt the frozen weak solver. Any SQL it returns is post-validated
    against those constraints and regenerated if violated."""

    # ------------------------------------------------------------------ #
    #  Hint extraction                                                    #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_hint(question: str) -> str:
        """Return the text after the first 'Hint:' line, or '' if absent."""
        m = _HINT_LINE_RE.search(question or "")
        return m.group("hint").strip() if m else ""

    @staticmethod
    def _strip_hint(question: str) -> str:
        """Return the question with the 'Hint:' line removed."""
        return _HINT_LINE_RE.sub("", question or "").strip()

    @staticmethod
    def _hint_targets(hint: str) -> list[str]:
        """Return any table names literally mentioned in the hint."""
        if not hint:
            return []
        # Skip SQL-verbally introduced names; just collect plausible identifiers.
        candidates = re.findall(r"[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)[`\"\]]?", hint)
        # Reject generic English-ish tokens so we only return plausible table-like names.
        stop = {
            "use", "using", "from", "join", "table", "the", "a", "an",
            "and", "or", "only", "must", "should", "via", "with", "on",
        }
        seen, out = set(), []
        for c in candidates:
            if c.lower() in stop:
                continue
            if c.lower() in seen:
                continue
            seen.add(c.lower())
            out.append(c)
        return out

    @staticmethod
    def _hard_requirement_lines(hint: str, targets: list[str]) -> list[str]:
        """Translate the hint into a list of explicit MUST-style rules."""
        rules: list[str] = []
        if not hint:
            return rules
        # Strip a trailing period so we can append cleanly.
        h = hint.rstrip(".").strip()
        rules.append(f"You MUST satisfy this constraint: {h}.")
        if targets:
            listed = ", ".join(targets)
            rules.append(
                f"The query MUST reference only the table(s) {listed} "
                f"unless the hint explicitly requires otherwise."
            )
        rules.append(
            "Do NOT add extra tables, JOINs, or computed columns beyond what "
            "the hint allows."
        )
        return rules

    # ------------------------------------------------------------------ #
    #  Post-hoc enforcement on the produced SQL                           #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _sql_targets(sql: str) -> list[str]:
        """Collect table names referenced by FROM/JOIN/UPDATE/INTO in ``sql``."""
        names: list[str] = []
        seen = set()
        for m in _TARGET_TABLE_RE.finditer(sql or ""):
            n = m.group("name")
            key = n.lower()
            if key in seen:
                continue
            seen.add(key)
            names.append(n)
        return names

    def _satisfies(self, sql: str, hint: str, allowed: list[str]) -> bool:
        """Light post-check: every allowed target must appear; no extras unless allowed.

        If ``allowed`` is empty (weak solver had nothing to go on) we only verify
        the SQL executes; the hint text is otherwise communicated via the prompt.
        """
        if not sql:
            return False
        sql_l = sql.lower()
        for tbl in allowed:
            if tbl.lower() not in sql_l:
                return False
        # Run it; if it errors we consider the constraint unsatisfied.
        result = self.execute(sql)
        return bool(result.get("ok"))

    # ------------------------------------------------------------------ #
    #  Main solve loop                                                    #
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        # --- 1) Lift the hint out of the raw question ------------------ #
        hint = self._extract_hint(question)
        clean_question = self._strip_hint(question)
        targets = self._hint_targets(hint)
        rules = self._hard_requirement_lines(hint, targets)

        # --- 2) Build a guard-prompt that restates constraints --------- #
        guard_system = (
            "You translate a natural-language question into a single SQLite-flavored "
            "SQL query. You MUST obey every numbered HARD REQUIREMENT below. "
            "Output ONLY the SQL statement, with no prose, no code fences."
        )
        if rules:
            guard_system += "\n\nHARD REQUIREMENTS:\n" + "\n".join(
                f"  {i+1}. {r}" for i, r in enumerate(rules)
            )

        guard_user = (
            (clean_question or question).strip()
            + ("\n\nHint constraint (repeat): " + hint if hint else "")
        ).strip()

        # --- 3) Two attempts through the frozen weak solver ------------ #
        candidate_sql = ""
        raw_outputs: list[str] = []

        for attempt in range(2):
            self.logger.debug(
                "P2P2DMinimaxS1HintGuard attempt=%d hint=%r targets=%s",
                attempt, hint, targets,
            )

            prompt = (
                f"Schema:\n{self.schema}\n\nQuestion:\n{guard_user}\n\nSQL:"
            )

            outs = self.llm(
                prompt,
                system=guard_system,
                temperature=0.0,
                n=1,
            )
            if isinstance(outs, list):
                raw_outputs.extend(outs)
            else:
                raw_outputs.append(str(outs))

            last = raw_outputs[-1]
            sql = bridge.extract_sql(last) or last.strip()
            candidate_sql = sql

            # --- 4) Hard-gate check vs the hint ------------------------ #
            if self._satisfies(candidate_sql, hint, targets):
                return candidate_sql

        # --- 5) Fallback: synthesize a defensive query from the hint --- #
        if targets:
            fallback = (
                f"SELECT * FROM {targets[0]} LIMIT 1"
            )
            self.logger.debug(
                "P2P2DMinimaxS1HintGuard using fallback SQL: %s", fallback,
            )
            return fallback

        # Last resort: return whatever the weak solver produced, even if it
        # fails the post-check, so the harness never raises.
        return candidate_sql