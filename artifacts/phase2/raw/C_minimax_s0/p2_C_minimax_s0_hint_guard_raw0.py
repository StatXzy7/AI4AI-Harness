"""Wraps a frozen weak solver by parsing Hint: lines from the question and enforcing their constraints as hard pre-SQL requirements before delegating to the base solver."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


_HINT_RE = re.compile(r"(?im)^\s*hint\s*:\s*(.+?)\s*$")


class P2P2CMinimaxS0HintGuard(SQLHarness):
    """Strategy P2P2C: parse 'Hint:' line(s) from the question, restate the
    constraints as hard guard requirements, and instruct the frozen weak
    solver that any SQL violating them will be rejected.  The guard is enforced
    in code (not only in the prompt) by post-validating the candidate SQL
    against the parsed hint constraints before returning it."""

    # ------------------------------------------------------------------ #
    # Hint parsing utilities
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_hints(question: str) -> Tuple[List[str], str]:
        """Return (hints, question_without_hint_lines).

        Hints are extracted case-insensitively from lines that begin with
        'Hint:'.  Multiple hint lines are supported.
        """
        hints: List[str] = []
        remaining_lines: List[str] = []
        for line in question.splitlines():
            m = _HINT_RE.match(line)
            if m:
                hints.append(m.group(1).strip())
            else:
                remaining_lines.append(line)
        cleaned = "\n".join(remaining_lines).strip()
        return hints, cleaned

    @staticmethod
    def _hint_to_constraints(hint: str) -> List[str]:
        """Translate a free-form hint into a list of human-readable,
        enforceable constraint statements.

        Heuristic pass -- not perfect, but good enough to act as guard rails
        that the post-check can detect common violations of.
        """
        constraints: List[str] = []
        h = hint.strip().rstrip(".")
        if not h:
            return constraints

        h_low = h.lower()

        # Table-related hints
        m = re.search(r"from\s+(?:the\s+)?[`'\"]?(\w+)[`'\"]?\s+table", h_low)
        if m:
            constraints.append(f"SQL MUST read from the `{m.group(1)}` table.")
        elif re.search(r"\buse\s+the\s+(\w+)\s+table\b", h_low):
            mm = re.search(r"\buse\s+the\s+(\w+)\s+table\b", h_low)
            constraints.append(f"SQL MUST read from the `{mm.group(1)}` table.")

        # Aggregate / function hints
        if re.search(r"\b(count|sum|avg|average|min|max|total)\b", h_low):
            constraints.append("SQL MUST use an aggregate function as implied by the hint.")

        # DISTINCT
        if re.search(r"\bdistinct\b|\bunique\b|\bno duplicates\b|\bdedup", h_low):
            constraints.append("SQL MUST use SELECT DISTINCT (or equivalent deduplication).")

        # ORDER BY / LIMIT / TOP
        if re.search(r"\b(top|first|highest|largest|maximum|max)\s+\d+", h_low):
            mm = re.search(r"\b(?:top|first|highest|largest|maximum|max)\s+(\d+)", h_low)
            constraints.append(f"SQL MUST return only the top {mm.group(1)} rows (ORDER BY ... LIMIT).")
        if re.search(r"\b(sort|order|rank)\b.*\b(asc|ascending|desc|descending)\b", h_low):
            mm = re.search(r"\b(asc|ascending|desc|descending)\b", h_low)
            constraints.append(f"SQL MUST include ORDER BY ... {mm.group(1).upper()}.")
        elif re.search(r"\b(highest|largest|biggest|top|maximum|max)\b", h_low):
            constraints.append("SQL MUST include ORDER BY ... DESC on the relevant column.")
        elif re.search(r"\b(lowest|smallest|minimum|min|bottom)\b", h_low):
            constraints.append("SQL MUST include ORDER BY ... ASC on the relevant column.")

        # GROUP BY
        if re.search(r"\b(group\s+by|per|each|for every)\b", h_low):
            constraints.append("SQL MUST use GROUP BY when grouping is implied.")

        # JOIN
        mjoin = re.search(r"\bjoin\s+(?:the\s+)?(\w+)\b", h_low)
        if mjoin:
            constraints.append(f"SQL MUST JOIN the `{mjoin.group(1)}` table.")

        # Filter / WHERE
        if re.search(r"\b(where|filter|only|with|having|where\s+clause)\b", h_low):
            constraints.append("SQL MUST include a WHERE (or HAVING) filter as implied.")

        # Comparison hints like "> 10", "= 5", "less than 100"
        mcomp = re.search(r"(>=|<=|!=|=|<>|>|<)\s*([0-9]+(?:\.[0-9]+)?)", h)
        if mcomp:
            constraints.append(f"SQL MUST enforce the comparison `{mcomp.group(0)}`.")
        mcomp2 = re.search(r"(greater than|less than|at least|at most|equal to)\s+([0-9]+(?:\.[0-9]+)?)", h_low)
        if mcomp2:
            constraints.append(f"SQL MUST enforce `{mcomp2.group(0)}`.")

        # If we could not extract any structured constraint, keep the whole
        # hint as a free-form constraint so the model still sees it.
        if not constraints:
            constraints.append(f"SQL MUST satisfy the following hint verbatim: {h!r}.")
        return constraints

    # ------------------------------------------------------------------ #
    # Guard / verification helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalise(sql: str) -> str:
        return re.sub(r"\s+", " ", sql or "").strip().lower()

    def _verify(self, sql: str, constraints: List[str]) -> Tuple[bool, str]:
        """Light-weight textual verification that the candidate SQL appears
        consistent with the parsed hint constraints.  This is a guard, not a
        full parser; it errs on the permissive side when in doubt.
        """
        norm = self._normalise(sql)
        if not norm:
            return False, "empty SQL"

        for c in constraints:
            cl = c.lower()

            # ---- table-from hint ----
            mm = re.search(r"sql must read from the `(\w+)` table", cl)
            if mm:
                tbl = mm.group(1)
                # The table name should appear after FROM / JOIN.
                if not re.search(rf"\b(from|join)\s+`?{re.escape(tbl)}`?\b", norm):
                    return False, f"hint guard: table `{tbl}` not used"

            # ---- JOIN hint ----
            mm = re.search(r"sql must join the `(\w+)` table", cl)
            if mm:
                tbl = mm.group(1)
                if not re.search(rf"\bjoin\s+`?{re.escape(tbl)}`?\b", norm):
                    return False, f"hint guard: join with `{tbl}` missing"

            # ---- aggregate hint ----
            if "must use an aggregate function" in cl:
                if not re.search(r"\b(count|sum|avg|min|max)\s*\(", norm):
                    return False, "hint guard: aggregate function missing"

            # ---- DISTINCT hint ----
            if "must use select distinct" in cl:
                if "distinct" not in norm:
                    return False, "hint guard: DISTINCT missing"

            # ---- ORDER BY ... DESC / ASC hint ----
            if "order by" in cl and ("desc" in cl or "asc" in cl):
                direction = "desc" if "desc" in cl else "asc"
                m = re.search(r"order\s+by[^;]*?\b(desc|asc)\b", norm)
                if not m:
                    return False, f"hint guard: ORDER BY ... {direction.upper()} missing"
                if m.group(1) != direction:
                    return False, f"hint guard: ORDER BY direction is {m.group(1).upper()}, expected {direction.upper()}"

            # ---- TOP N / LIMIT N hint ----
            mm = re.search(r"top\s+(\d+)\s+rows", cl)
            if mm:
                n = mm.group(1)
                if not re.search(rf"\b(limit\s+{n}\b|fetch\s+first\s+{n}\b|top\s+{n}\b)", norm):
                    return False, f"hint guard: TOP/LIMIT {n} missing"

            # ---- GROUP BY hint ----
            if "must use group by" in cl:
                if "group by" not in norm:
                    return False, "hint guard: GROUP BY missing"

            # ---- WHERE / HAVING hint ----
            if "must include a where" in cl or "must include a having" in cl:
                if not re.search(r"\b(where|having)\b", norm):
                    return False, "hint guard: WHERE/HAVING filter missing"

            # ---- Comparison hint ----
            mcomp = re.search(r"enforce (?:the comparison )?`?([^`]+)`?", cl)
            if mcomp and any(op in mcomp.group(1) for op in (">", "<", "=", "!")):
                token = mcomp.group(1).strip().rstrip(";").replace(" ", "")
                # Normalise SQL: strip spaces around operators
                sql_cmp = re.sub(r"\s*([><=!]+)\s*", r"\1", norm)
                if token.replace(" ", "") not in sql_cmp:
                    return False, f"hint guard: comparison `{token}` not present"

        return True, "ok"

    # ------------------------------------------------------------------ #
    # Main solve
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        hints, cleaned_question = self._parse_hints(question)

        # Build a structured guard instruction that the frozen solver MUST
        # satisfy, in addition to the original question.
        if hints:
            constraint_lines: List[str] = []
            for i, h in enumerate(hints, 1):
                cs = self._hint_to_constraints(h)
                constraint_lines.append(f"Hint {i}: {h}")
                for j, c in enumerate(cs, 1):
                    constraint_lines.append(f"  - Constraint {i}.{j}: {c}")
            guard_block = (
                "HARD REQUIREMENTS (derived from the user's Hint: lines; "
                "ANY SQL that violates these MUST be rejected and re-written):\n"
                + "\n".join(constraint_lines)
                + "\nYou MUST produce SQL that satisfies every constraint above."
            )
        else:
            guard_block = ""

        system_prompt = (
            "You are a Text-to-SQL generator. You must produce a single, "
            "syntactically valid SQL query that answers the user's question. "
            "If the question contains a 'Hint:' line, the hint is a HARD "
            "requirement; the SQL you produce MUST honour it. Output ONLY the "
            "SQL inside a single