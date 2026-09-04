"""Harness that parses the 'Hint:' line(s) from the question, restates them as numbered hard requirements injected into the generation prompt, then guards the candidate SQL with deterministic directive/literal checks and an LLM compliance judge inside a bounded repair loop."""

import re
from typing import List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2HintGuard(SQLHarness):
    """Restate hint constraints as hard requirements and guard SQL against them."""

    MAX_ATTEMPTS = 3

    _HINT_RE = re.compile(r"hint\s*\d*\s*[:：\-]\s*(.+)", re.IGNORECASE)

    # (pattern that triggers the directive when seen in a requirement,
    #  pattern the SQL must then contain, human-readable label)
    _DIRECTIVES: Tuple[Tuple[str, str, str], ...] = (
        (r"\border\s+by\b|\bsort(?:ed|ing)?\b", r"\border\s+by\b", "ORDER BY"),
        (r"\bdescending\b|\bdesc\b|\bhighest\b|\blargest\b|\bgreatest\b", r"\bdesc\b|\bmax\s*\(", "DESC/MAX"),
        (r"\btop\s+\d+\b|\bfirst\s+\d+\b|\blimit\b", r"\blimit\b", "LIMIT"),
        (r"\bgroup\s+by\b|\bper\s+\w+\b|\beach\b|\bfor\s+every\b", r"\bgroup\s+by\b", "GROUP BY"),
        (r"\bhaving\b", r"\bhaving\b", "HAVING"),
        (r"\bdistinct\b|\bunique\b", r"\bdistinct\b", "DISTINCT"),
        (r"\bcount\b|\bnumber\s+of\b|\bhow\s+many\b", r"\bcount\s*\(", "COUNT"),
        (r"\bsum\b|\btotal\b", r"\bsum\s*\(", "SUM"),
        (r"\baverage\b|\bavg\b|\bmean\b", r"\bavg\s*\(", "AVG"),
        (r"\bmaximum\b|\bmax\b", r"\bmax\s*\(", "MAX"),
        (r"\bminimum\b|\bmin\b", r"\bmin\s*\(", "MIN"),
        (r"\bbetween\b", r"\bbetween\b", "BETWEEN"),
        (r"\bjoin\b|\bcombined\s+with\b|\balong\s+with\b", r"\bjoin\b", "JOIN"),
        (r"\bexclude\b|\bnot\s+in\b|\bexcept\b", r"\bnot\b|\bexcept\b|\b<>|!=", "NOT IN/EXCEPT"),
    )

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        hints = self._parse_hints(question)
        requirements = self._restate_requirements(question, hints) if hints else []
        requirement_block = self._format_requirements(requirements)

        system = (
            "You are an expert Text-to-SQL engine. You obey every stated hard "
            "requirement exactly and output only a single SQL query."
        )
        base_prompt = self._build_generation_prompt(question, requirement_block)

        attempts = self.MAX_ATTEMPTS if requirements else 1
        sql = ""
        feedback = ""
        for _ in range(attempts):
            prompt = base_prompt if not feedback else base_prompt + "\n\n" + feedback
            raw = self._call_llm(prompt, system=system)
            candidate = self._extract_sql(raw)
            if not candidate:
                continue
            sql = candidate
            if not requirements:
                break
            violations = self._find_violations(sql, requirements)
            if not violations:
                break
            feedback = self._build_feedback(sql, violations)

        return sql if sql else "SELECT 1"

    # ------------------------------------------------------- hint handling

    @classmethod
    def _parse_hints(cls, question: str) -> List[str]:
        """Extract the text of every 'Hint:' line from the question."""
        hints: List[str] = []
        for line in question.splitlines():
            m = cls._HINT_RE.search(line)
            if m:
                hint = m.group(1).strip()
                if hint and hint not in hints:
                    hints.append(hint)
        return hints

    def _restate_requirements(self, question: str, hints: List[str]) -> List[str]:
        """Use the LLM to restate hint constraints as explicit hard requirements."""
        hint_text = "\n".join("- " + h for h in hints)
        prompt = (
            "You are given a Text-to-SQL question and its hint line(s).\n"
            "Restate every constraint, filter, computation, ordering, or directive "
            "contained in the hints as a numbered list of HARD REQUIREMENTS that a "
            "correct SQL query MUST satisfy. Be specific: name exact columns, values, "
            "aggregations, orderings, and limits implied by the hints.\n"
            "Output ONLY the numbered list, one requirement per line.\n\n"
            "Question:\n" + question + "\n\n"
            "Hint line(s):\n" + hint_text + "\n\n"
            "HARD REQUIREMENTS:"
        )
        text = self._call_llm(prompt, system="You extract precise SQL requirements from hints.")
        requirements = self._parse_numbered_list(text)
        if not requirements:
            requirements = list(hints)  # fallback: treat each hint verbatim as a requirement
        return requirements[:12]

    @staticmethod
    def _parse_numbered_list(text: str) -> List[str]:
        items: List[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(?:\d+\s*[.)]\s*|[-*•]\s+)(.+)$", line)
            if m:
                item = m.group(1).strip()
                if item:
                    items.append(item)
        return items

    @staticmethod
    def _format_requirements(requirements: List[str]) -> str:
        if not requirements:
            return ""
        lines = ["HARD REQUIREMENTS (the SQL query MUST satisfy ALL of the following):"]
        for i, req in enumerate(requirements, 1):
            lines.append("%d. %s" % (i, req))
        return "\n".join(lines)

    # ------------------------------------------------------- prompt build

    def _build_generation_prompt(self, question: str, requirement_block: str) -> str:
        parts = [
            "Database schema:",
            self.schema,
            "",
            "Question:",
            question,
        ]
        if requirement_block:
            parts += ["", requirement_block]
        parts += [
            "",
            "Write a single SQL query that answers the question and satisfies every "
            "hard requirement above. Output only the SQL query.",
        ]
        return "\n".join(parts)

    # ------------------------------------------------------------- guard

    def _find_violations(self, sql: str, requirements: List[str]) -> List[str]:
        """Deterministic checks first; only if they pass, consult the LLM judge."""
        violations = self._heuristic_violations(sql, requirements)
        if violations:
            return violations
        return self._judge_violations(sql, requirements)

    @classmethod
    def _heuristic_violations(cls, sql: str, requirements: List[str]) -> List[str]:
        violations: List[str] = []
        sql_l = sql.lower()
        for i, req in enumerate(requirements, 1):
            req_l = req.lower()
            for req_pat, sql_pat, label in cls._DIRECTIVES:
                if re.search(req_pat, req_l) and not re.search(sql_pat, sql_l):
                    violations.append(
                        "Requirement %d implies %s but the SQL lacks it: %s" % (i, label, req)
                    )
            for literal in re.findall(r"[\"'`]([^\"'`]+)[\"'`]", req):
                if literal and literal.lower() not in sql_l:
                    violations.append(
                        "Requirement %d references '%s' which is absent from the SQL: %s"
                        % (i, literal, req)
                    )
        return violations

    def _judge_violations(self, sql: str, requirements: List[str]) -> List[str]:
        prompt = (
            "You are a strict SQL compliance reviewer.\n\n"
            "Database schema:\n" + self.schema + "\n\n"
            + self._format_requirements(requirements) + "\n\n"
            "SQL under review:\n