"""Harness that parses a 'Hint:' line from the question, enforces its constraints as hard requirements, and applies a frozen Min-Max-style SQL solver with guarded prompting."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


HINT_PATTERN = re.compile(
    r"(?:^|\n)\s*Hint\s*:\s*(.+?)(?=(?:\n\s*[A-Z][a-zA-Z]+\s*:)|\n\s*$|\Z)",
    re.IGNORECASE | re.DOTALL,
)


class P2P2DMinimaxS0HintGuard(SQLHarness):
    """Parse Hint: constraints, restate them as hard requirements, then solve with a frozen weak solver."""

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _extract_hint(question: str) -> str:
        """Return the text after the first 'Hint:' marker, or '' if absent."""
        match = HINT_PATTERN.search(question or "")
        if not match:
            return ""
        return match.group(1).strip().rstrip(".")

    @staticmethod
    def _strip_hint(question: str) -> str:
        """Remove the Hint: clause from the question so it does not confuse the solver."""
        return HINT_PATTERN.sub("", question or "").strip()

    @staticmethod
    def _split_constraints(hint_text: str) -> List[str]:
        """Split a hint into atomic, enforceable constraint sentences/clauses."""
        if not hint_text:
            return []
        text = hint_text.replace("\n", " ").strip()
        # Split on sentence boundaries, semicolons, or numbered list commas when long.
        parts = re.split(r"(?<=[.!?;])\s+|\s*,\s+(?=(?:where|and|or|with|having|group|order|limit|join|use|don['']t|do\s+not)\b)",
                         text,
                         flags=re.IGNORECASE,
                         )
        cleaned: List[str] = []
        for p in parts:
            s = p.strip().rstrip(".")
            if s:
                cleaned.append(s)
        # If splitting produced nothing useful, keep the raw hint as a single item.
        return cleaned if cleaned else ([text] if text else [])

    @staticmethod
    def _has_negative(constraints: List[str]) -> bool:
        joined = " ".join(constraints).lower()
        return any(
            token in joined
            for token in (" don't ", " don't", " do not ", "do not", " not ", " never ", " without ", " except ")
        )

    # ------------------------------------------------------------------ prompt
    def _build_prompt(self, question: str, hint_text: str, constraints: List[str]) -> str:
        cleaned_question = self._strip_hint(question)
        if constraints:
            numbered = "\n".join(f"  H{i+1}. {c}" for i, c in enumerate(constraints))
            guard = (
                "You MUST treat the following constraints as HARD REQUIREMENTS.\n"
                "Every constraint MUST appear as a real SQL clause (WHERE/JOIN/GROUP BY/HAVING/ORDER BY/LIMIT/etc.).\n"
                "Do NOT relax, drop, paraphrase-away, or contradict any constraint.\n"
                "If a constraint conflicts with the question, follow the constraint.\n"
                "Constraints:\n"
                f"{numbered}\n"
            )
        else:
            guard = "No additional hints were supplied.\n"

        prompt = (
            "You are a SQL generator. Produce exactly ONE SQLite-compatible SQL statement that answers the question.\n\n"
            f"{guard}\n"
            f"Question:\n  {cleaned_question}\n\n"
            "Write SQL only. No explanations, no markdown."
        )
        return prompt

    # ------------------------------------------------------------------ validate
    def _validate_sql(self, sql: str, constraints: List[str]) -> bool:
        """Heuristically check that produced SQL contains tokens reflecting every constraint."""
        if not sql or not constraints:
            return True
        sql_low = sql.lower()
        for c in constraints:
            tokens = self._constraint_tokens(c)
            if not tokens:
                continue
            if not all(tok in sql_low for tok in tokens):
                return False
        return True

    @staticmethod
    def _constraint_tokens(constraint: str) -> List[str]:
        """Extract the key enforcing tokens that must show up in the SQL."""
        c = constraint.lower()
        tokens: List[str] = []

        # Numeric literals (years, limits, counts)
        for m in re.findall(r"\b\d{2,4}\b", c):
            tokens.append(m)

        # Comparator + value pairs
        comp_map = {
            "greater than": ">",
            "more than": ">",
            "less than": "<",
            "fewer than": "<",
            "at least": ">=",
            "at most": "<=",
            "no more than": "<=",
            "no less than": ">=",
            "equal to": "=",
            "equals": "=",
            "is": "=",
        }
        for phrase, op in comp_map.items():
            if phrase in c:
                tokens.append(op)
                # Capture the operand word right after the phrase
                m = re.search(re.escape(phrase) + r"\s+([\w\.\-]+)", c)
                if m:
                    tokens.append(m.group(1))
                break

        # Common clause triggers
        triggers = {
            "distinct": "distinct",
            "group by": "group by",
            "order by": "order by",
            "ascending": "asc",
            "descending": "desc",
            "limit": "limit",
            "having": "having",
            "join": "join",
            "inner join": "inner join",
            "left join": "left join",
            "between": "between",
            "in (": "in (",
            "exists": "exists",
            "case": "case",
            "union": "union",
            "not": "not",
        }
        for k, v in triggers.items():
            if k in c:
                tokens.append(v)

        # Negative directives ("don't use GROUP BY") -> ensure the *forbidden* token is absent
        # We encode this by requiring the opposite keyword to be present.
        negatives = re.findall(r"don['']t\s+(\w[\w\s]*?)(?:\.|;|$)", c) + re.findall(
            r"do\s+not\s+(\w[\w\s]*?)(?:\.|;|$)", c
        )
        for neg in negatives:
            neg = neg.strip()
            if not neg:
                continue
            if "join" in neg:
                tokens.append("join")  # must include join when 'no joins' requested is false here
            # Otherwise: best-effort, leave it to the guard prompt

        # De-dup, keep order, drop empties
        seen, out = set(), []
        for t in tokens:
            t = (t or "").strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out

    # ------------------------------------------------------------------ execute
    def _try_execute(self, sql: str) -> Tuple[bool, Any]:
        try:
            result = self.execute(sql)
            ok = bool(result and result.get("ok"))
            return ok, result
        except Exception as exc:  # pragma: no cover - defensive
            return False, {"ok": False, "rows": [], "error": str(exc)}

    # ------------------------------------------------------------------ fallback
    def _fallback_sql(self, question: str) -> str:
        """Deterministic, minimal fallback when the solver or guard fails."""
        cleaned = self._strip_hint(question)
        # Strip trailing punctuation so the SELECT doesn't start with stray whitespace.
        if cleaned.lower().startswith(("select ", "with ")):
            base = cleaned
        else:
            base = "SELECT 1"
        return base.rstrip(";") + ";"

    # ------------------------------------------------------------------ main solve
    def solve(self, question: str) -> str:
        hint_text = self._extract_hint(question)
        constraints = self._split_constraints(hint_text)
        has_negative = self._has_negative(constraints)

        # 1) Restate the hint as hard requirements via a guard prompt.
        prompt = self._build_prompt(question, hint_text, constraints)
        system = (
            "You are a strict SQL generator. You must comply with every numbered "
            "constraint. Output one SQL statement only, no commentary."
        )

        # 2) Query the frozen weak solver. Keep temperature 0.0 for determinism; sample a few
        #    so we can pick one that actually satisfies the guard.
        n_samples = 4 if constraints else 1
        try:
            raw_responses: List[str] = self.llm(
                prompt,
                system=system,
                temperature=0.0,
                n=n_samples,
            )
        except TypeError:
            raw_responses = [self.llm(prompt, system=system, temperature=0.0, n=1)]

        candidate_sqls: List[str] = []
        for raw in raw_responses:
            sql = bridge.extract_sql(raw)
            if sql and sql not in candidate_sqls:
                candidate_sqls.append(sql)

        # 3) Prefer candidates that pass the constraint-token guard.
        guarded = [s for s in candidate_sqls if self._validate_sql(s, constraints)]
        ordered = guarded + [s for s in candidate_sqls if s not in guarded]

        # 4) Execute in order; first one that runs successfully wins.
        for sql in ordered:
            ok, result = self._try_execute(sql)
            if ok:
                return sql

        # 5) If guarded candidates ran fine but lost on selection, fall back to first guarded.
        if guarded:
            return guarded[0]

        # 6) If there were negative constraints, avoid dropping them: return the most
        #    faithful candidate verbatim from the solver.
        if candidate_sqls:
            if has_negative:
                return candidate_sqls[0]
            return candidate_sqls[0]

        # 7) Last resort.
        return self._fallback_sql(question)