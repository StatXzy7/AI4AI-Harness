"""Hint-Guard harness that parses the 'Hint:' line from the question, restates it as hard requirements in an explicit pre-pass before SQL generation, and then guard-repairs the SQL until those requirements and a test execution both pass."""

import re
from typing import Dict, List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS1HintGuard(SQLHarness):
    """P2P2C pipeline: Parse hint -> Phrase hard requirements -> Produce SQL -> Check/guard & repair."""

    MAX_REPAIR_ATTEMPTS = 3
    MAX_EXEC_ATTEMPTS = 3

    _HINT_RE = re.compile(r"hint\s*[:\-]\s*(.+)", re.IGNORECASE | re.DOTALL)
    _QUOTED_RE = re.compile(r"'([^'\n]+)'|\"([^\"\n]+)\"")
    _BACKTICK_RE = re.compile(r"`([^`\n]+)`")
    _NUMERIC_KV_RE = re.compile(r"\b[A-Za-z_][\w. ]{0,40}?=\s*(\d+(?:\.\d+)?)\b")
    _DESC_RE = re.compile(r"\bdesc(?:ending)?\b", re.IGNORECASE)
    _LIMIT_RE = re.compile(
        r"\b(?:top|limit|first)\s+(\d+)\b|\b(\d+)\s+(?:rows|records|entries|results)\b",
        re.IGNORECASE,
    )
    _ORDER_RE = re.compile(r"\border(?:ed)?\s+by\b|\bsort(?:ed)?\s+by\b", re.IGNORECASE)

    _GEN_SYSTEM = (
        "You are an expert Text-to-SQL engine. You output exactly one SQL query. "
        "HARD REQUIREMENTS are mandatory and override your own assumptions."
    )
    _RESTATE_SYSTEM = (
        "You are a meticulous requirements analyst for Text-to-SQL tasks. You never "
        "write SQL; you only restate constraints precisely and completely."
    )

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        question = question or ""

        # P1 -- Parse the 'Hint:' line out of the question (control flow, not prompt).
        hint = self._parse_hint(question)

        # P2 -- Phrase/restate the hint as HARD REQUIREMENTS *before* writing SQL.
        restated = self._restate_requirements(question, hint)
        constraints = self._extract_checkable_constraints(hint)
        hard_block = self._format_hard_requirements(restated, constraints)

        # P3 -- Produce SQL conditioned on schema + hard requirements + question.
        sql = self._generate_sql(question, hard_block)

        # C -- Check: constraint guard with bounded repair.
        sql = self._constraint_guard(sql, question, hard_block, constraints)

        # C -- Check: execution guard with bounded repair.
        sql = self._execution_guard(sql, question, hard_block)

        # Final reconciliation: never return SQL that silently drops a hard requirement.
        if constraints and self._check_constraints(sql, constraints):
            sql = self._constraint_guard(sql, question, hard_block, constraints)

        return sql

    # ------------------------------------------------------------- P1: parse

    def _parse_hint(self, question: str) -> str:
        match = self._HINT_RE.search(question)
        if not match:
            return ""
        hint = match.group(1)
        # The hint block ends at the first blank line (or end of question).
        hint = re.split(r"\n\s*\n", hint, maxsplit=1)[0]
        return hint.strip()

    # ---------------------------------------------------------- P2: restate

    def _restate_requirements(self, question: str, hint: str) -> str:
        if not hint:
            return ""
        prompt = (
            "Database schema:\n" + (self.schema or "") + "\n\n"
            "Question:\n" + question + "\n\n"
            "Hint parsed from the question:\n" + hint + "\n\n"
            "Task: Restate EVERY piece of information in the hint as a numbered "
            "list of HARD REQUIREMENTS that the SQL query MUST satisfy. Cover "
            "filter values, columns, tables, joins, comparisons, ordering, and "
            "row limits. Do not write SQL. Output only the numbered list."
        )
        return self._call_llm(prompt, system=self._RESTATE_SYSTEM)

    def _extract_checkable_constraints(self, hint: str) -> List[Dict[str, str]]:
        """Turn the hint into machine-checkable constraints for the guard."""
        constraints: List[Dict[str, str]] = []
        if not hint:
            return constraints

        for m in self._QUOTED_RE.finditer(hint):
            literal = (m.group(1) or m.group(2) or "").strip()
            if literal:
                constraints.append({
                    "kind": "token",
                    "value": literal,
                    "desc": "SQL must reference the hint literal '%s'." % literal,
                })

        for m in self._BACKTICK_RE.finditer(hint):
            ident = m.group(1).strip()
            if ident:
                constraints.append({
                    "kind": "token",
                    "value": ident,
                    "desc": "SQL must use the schema element `%s` named in the hint." % ident,
                })

        for m in self._NUMERIC_KV_RE.finditer(hint):
            num = m.group(1)
            constraints.append({
                "kind": "token",
                "value": num,
                "desc": "SQL must apply the hint comparison value %s." % num,
            })

        if self._DESC_RE.search(hint):
            constraints.append({
                "kind": "keyword",
                "value": "DESC",
                "desc": "SQL must sort descending (DESC), as the hint requires.",
            })

        m = self._LIMIT_RE.search(hint)
        if m:
            n = m.group(1) or m.group(2)
            constraints.append({
                "kind": "keyword",
                "value": "LIMIT",
                "desc": "SQL must include a LIMIT clause (the hint asks for %s rows)." % n,
            })

        if self._ORDER_RE.search(hint):
            constraints.append({
                "kind": "keyword",
                "value": "ORDER BY",
                "desc": "SQL must include an ORDER BY clause, as the hint requires.",
            })

        # De-duplicate while preserving order.
        seen = set()
        unique: List[Dict[str, str]] = []
        for c in constraints:
            key = (c["kind"], c["value"].lower())
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    def _format_hard_requirements(self, restated: str,
                                  constraints: List[Dict[str, str]]) -> str:
        if not restated and not constraints:
            return ""
        lines = [
            "HARD REQUIREMENTS (restated from the hint; the SQL MUST satisfy ALL of them):"
        ]
        if restated:
            lines.append(restated)
        if constraints:
            lines.append("Machine-checkable requirements:")
            for c in constraints:
                lines.append("- " + c["desc"])
        return "\n".join(lines) + "\n\n"

    # ---------------------------------------------------------- P3: produce

    def _generate_sql(self, question: str, hard_block: str) -> str:
        # Hard requirements are placed BEFORE the question so they are read first.
        prompt = (
            "Database schema:\n" + (self.schema or "") + "\n\n"
            + hard_block
            + "Question:\n" + question + "\n\n"
            "Write ONE SQL query that answers the question and satisfies EVERY "
            "hard requirement above. Output only the SQL query."
        )
        raw = self._call_llm(prompt, system=self._GEN_SYSTEM)
        return self._to_sql(raw)

    # --------------------------------------------------------------- C: guard

    def _check_constraints(self, sql: str,
                           constraints: List[Dict[str, str]]) -> List[str]:
        if not sql.strip():
            return ["No SQL was produced."]
        low = sql.lower()
        violations: List[str] = []
        for c in constraints:
            if c["kind"] == "token":
                if c["value"].lower() not in low:
                    violations.append(c["desc"])
            else:  # keyword constraint
                if not re.search(r"\b" + re.escape(c["value"].lower()) + r"\b", low):
                    violations.append(c["desc"])
        return violations

    def _constraint_guard(self, sql: str, question: str, hard_block: str,
                          constraints: List[Dict[str, str]]) -> str:
        if not constraints:
            return sql
        best = sql
        for _ in range(self.MAX_REPAIR_ATTEMPTS):
            violations = self._check_constraints(best, constraints)
            if not violations:
                return best
            prompt = (
                "Database schema:\n" + (self.schema or "") + "\n\n"
                + hard_block
                + "Question:\n" + question + "\n\n"
                "Current SQL:\n" + best + "\n\n"
                "The current SQL VIOLATES these hard requirements:\n"
                + "\n".join("- " + v for v in violations)
                + "\n\nRewrite the SQL so that it answers the question and "
                "satisfies EVERY hard requirement. Output only the corrected SQL."
            )
            fixed = self._to_sql(self._call_llm(prompt, system=self._GEN_SYSTEM))
            if not fixed.strip() or fixed.strip() == best.strip():
                break
            best = fixed
        return best

    def _execution_guard(self, sql: str, question: str, hard_block: str) -> str:
        best = sql
        for _ in range(self.MAX_EXEC_ATTEMPTS):
            if not best.strip():
                break
            try:
                result = self.execute(best)
            except Exception as exc:  # defensive: exec must not crash the harness
                result = {"ok": False, "rows": [], "error": str(exc)}
            if result.get("ok"):
                return best
            prompt = (
                "Database schema:\n" + (self.schema or "") + "\n\n"
                + hard_block
                + "Question:\n" + question + "\n\n"
                "This SQL failed to execute:\n" + best + "\n\n"
                "Database error:\n" + str(result.get("error", "unknown error")) + "\n\n"
                "Fix the SQL so it executes correctly AND still satisfies every "
                "hard requirement. Output only the corrected SQL."
            )
            fixed = self._to_sql(self._call_llm(prompt, system=self._GEN_SYSTEM))
            if not fixed.strip() or fixed.strip() == best.strip():
                break
            best = fixed
        return best

    # -------------------------------------------------------------- helpers

    def _call_llm(self, prompt: str, system: str = "") -> str:
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return (out or "").strip()

    @staticmethod
    def _to_sql(raw: str) -> str:
        sql = bridge.extract_sql(raw) if raw else ""
        if not sql:
            sql = (raw or "").strip()
        return sql.strip()