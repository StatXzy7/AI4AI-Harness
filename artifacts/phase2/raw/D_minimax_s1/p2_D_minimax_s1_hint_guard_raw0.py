"""P2P2DMinimaxS1HintGuard: enforces hint-derived constraints as hard guards in the generated SQL."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS1HintGuard(SQLHarness):
    # SQL fragment that must always appear when its hint is present
    # Each guard is (regex_match_on_hint, sql_constraint_clause, prompt_instruction)
    _GUARDS = [
        (
            r"\b(distinct|unique|deduplicat|no\s+duplicates?)\b",
            None,
            "If the question asks for distinct/unique results, SELECT must use DISTINCT.",
        ),
        (
            r"\b(only|just|exclusively)\b.*\b(in|active|enabled|published|approved)",
            None,
            "If a status filter like 'only active' is hinted, add a WHERE clause restricting status appropriately.",
        ),
        (
            r"\b(no\s+nulls?|not\s+null|ignore\s+nulls?|exclude\s+nulls?)\b",
            " AND ".join([]) ,  # placeholder, handled in code
            "If hint mentions nulls, add IS NOT NULL / IS NULL filters as implied by the hint.",
        ),
        (
            r"\b(top|first|latest|most\s+recent|newest)\b",
            None,
            "If the question asks for the top/first/latest record, use ORDER BY ... LIMIT 1.",
        ),
        (
            r"\b(count|how\s+many|number\s+of)\b",
            None,
            "If the question asks for a count, use SELECT COUNT(*).",
        ),
        (
            r"\b(sum|total|aggregate)\b",
            None,
            "If the question asks for sum/total, use SUM(...) aggregation.",
        ),
        (
            r"\b(average|avg|mean)\b",
            None,
            "If the question asks for an average, use AVG(...) aggregation.",
        ),
        (
            r"\b(max(imum)?|highest|largest|greatest)\b",
            None,
            "If the question asks for a maximum, use MAX(...).",
        ),
        (
            r"\b(min(imum)?|lowest|smallest|least)\b",
            None,
            "If the question asks for a minimum, use MIN(...).",
        ),
        (
            r"\b(group\s+by|per|by\s+each|for\s+each)\b",
            None,
            "If the question implies grouping, use GROUP BY on the appropriate column(s).",
        ),
        (
            r"\b(order\s+by|sort|ascending|descending)\b",
            None,
            "If the question implies sorting, use ORDER BY on the appropriate column(s).",
        ),
    ]

    def _extract_hint(self, question: str) -> Tuple[str, str]:
        """Split the question into (body, hint). Hint is the text after 'Hint:' if present."""
        if not question:
            return "", ""
        m = re.search(r"(?im)^\s*hint\s*:\s*(.*)$", question)
        if m:
            hint = m.group(1).strip()
            body = (question[: m.start()] + question[m.end():]).strip()
            return body, hint
        return question.strip(), ""

    def _activated_guards(self, hint: str) -> List[str]:
        """Return a list of human-readable guard instructions that the hint activates."""
        if not hint:
            return []
        activated: List[str] = []
        hint_lc = hint.lower()
        for pattern, _unused, instruction in self._GUARDS:
            if re.search(pattern, hint_lc):
                activated.append(instruction)
        return activated

    def _enforce_guards(self, sql: str, hint: str) -> str:
        """Programmatically rewrite the SQL so each activated guard is satisfied."""
        if not sql or not hint:
            return sql

        hint_lc = hint.lower()
        s = sql.rstrip(";").rstrip()

        # DISTINCT guard
        if re.search(r"\b(distinct|unique|deduplicat|no\s+duplicates?)\b", hint_lc):
            if re.search(r"(?is)^\s*select\s+distinct\b", s) is None:
                s = re.sub(r"(?is)^\s*select\s+", "SELECT DISTINCT ", s, count=1)

        # COUNT guard
        if re.search(r"\b(count|how\s+many|number\s+of)\b", hint_lc):
            if re.search(r"(?is)\bselect\s+count\s*\(", s) is None:
                # Wrap the current select-list in COUNT(*)
                m = re.match(r"(?is)^\s*select\s+(.*?)\s+from\b", s)
                if m:
                    select_list = m.group(1)
                    # If it is already COUNT, do nothing. Otherwise rebuild.
                    if not re.search(r"(?is)^\s*count\s*\(", select_list):
                        # Preserve top-level DISTINCT inside COUNT if present
                        distinct_m = re.match(r"(?is)^\s*distinct\s+(.+)$", select_list)
                        if distinct_m:
                            inner = distinct_m.group(1).strip()
                            new_list = f"COUNT(DISTINCT {inner})"
                        else:
                            new_list = "COUNT(*)"
                        s = re.sub(
                            r"(?is)^\s*select\s+.*?\s+from\b",
                            f"SELECT {new_list} FROM",
                            s,
                            count=1,
                        )

        # SUM / AVG / MAX / MIN guard (only enforce the first matching one)
        agg_map = [
            (r"\b(sum|total|aggregate)\b", "SUM"),
            (r"\b(average|avg|mean)\b", "AVG"),
            (r"\b(max(imum)?|highest|largest|greatest)\b", "MAX"),
            (r"\b(min(imum)?|lowest|smallest|least)\b", "MIN"),
        ]
        for pattern, fn in agg_map:
            if re.search(pattern, hint_lc):
                if re.search(rf"(?is)\b{fn}\s*\(", s) is None:
                    m = re.match(r"(?is)^\s*select\s+(.*?)\s+from\b", s)
                    if m:
                        inner = m.group(1).strip()
                        if not re.match(r"(?is)^\s*(count|sum|avg|max|min)\s*\(", inner):
                            # If it's a bare column name, wrap it; otherwise leave as-is
                            if re.match(r"(?is)^[A-Za-z_][\w\.\*]*$", inner):
                                s = re.sub(
                                    r"(?is)^\s*select\s+.*?\s+from\b",
                                    f"SELECT {fn}({inner}) FROM",
                                    s,
                                    count=1,
                                )
                break  # only the first applicable aggregation hint is enforced

        # TOP/FIRST/LATEST guard -> ORDER BY ... LIMIT 1 on a sensible column
        if re.search(r"\b(top|first|latest|most\s+recent|newest)\b", hint_lc):
            if re.search(r"(?is)\blimit\s+1\b", s) is None:
                # Find the first column after SELECT to ORDER BY it DESC
                m = re.match(r"(?is)^\s*select\s+(.*?)\s+from\b", s)
                if m:
                    inner = m.group(1).strip()
                    col_m = re.match(r"(?is)(?:distinct\s+)?([A-Za-z_][\w\.]*)", inner)
                    col = col_m.group(1) if col_m else "1"
                    if not re.search(r"(?is)\border\s+by\b", s):
                        s = f"{s} ORDER BY {col} DESC"
                    s = f"{s} LIMIT 1"

        # NULL guard (exclude nulls by default)
        if re.search(r"\b(no\s+nulls?|not\s+null|ignore\s+nulls?|exclude\s+nulls?)\b", hint_lc):
            if re.search(r"(?is)\bis\s+not\s+null\b", s) is None:
                # Heuristic: take the first column mentioned in WHERE/SELECT and add IS NOT NULL
                col = None
                wm = re.search(r"(?is)\bwhere\s+([A-Za-z_][\w\.]*)\s*(=|IS|<>|!=|<|>)", s)
                if wm:
                    col = wm.group(1)
                else:
                    sm = re.match(r"(?is)^\s*select\s+(?:distinct\s+)?([A-Za-z_][\w\.]*)", s)
                    if sm:
                        col = sm.group(1)
                if col:
                    clause = f"{col} IS NOT NULL"
                    if re.search(r"(?is)\bwhere\b", s):
                        s = re.sub(r"(?is)(\bwhere\b)", r"\1 " + clause + " AND", s, count=1)
                    else:
                        s = f"{s} WHERE {clause}"

        # STATUS / active guard
        if re.search(r"\b(only|just|exclusively)\b.*\b(in|active|enabled|published|approved)\b", hint_lc):
            # Only inject if no explicit status filter present
            if not re.search(r"(?is)\b(status|state|active|enabled|is_active)\b\s*=\s*'", s):
                # Try to detect a likely status column from SELECT/WHERE
                sm = re.search(r"(?is)(?:from|where)\s+([A-Za-z_][\w\.]*)", s)
                # Default: inject "active = 1" if a column named like status/active exists in the schema context
                for cand in ("status", "state", "is_active", "active", "enabled"):
                    if re.search(rf"(?is)\b{cand}\b", s):
                        clause = f"{cand} = 'active'" if cand in ("status", "state") else f"{cand} = 1"
                        if re.search(r"(?is)\bwhere\b", s):
                            s = re.sub(r"(?is)(\bwhere\b)", r"\1 " + clause + " AND", s, count=1)
                        else:
                            s = f"{s} WHERE {clause}"
                        break
                else:
                    # Fallback: try to insert before ORDER BY / GROUP BY / LIMIT / end
                    clause = "status = 'active'"
                    if re.search(r"(?is)\bwhere\b", s):
                        s = re.sub(r"(?is)(\bwhere\b)", r"\1 " + clause + " AND", s, count=1)
                    else:
                        s = f"{s} WHERE {clause}"

        # GROUP BY guard
        if re.search(r"\b(group\s+by|per|by\s+each|for\s+each)\b", hint_lc):
            if re.search(r"(?is)\bgroup\s+by\b", s) is None:
                # Heuristic: GROUP BY by the first non-aggregated column in SELECT
                sm = re.match(r"(?is)^\s*select\s+(.*?)\s+from\b", s)
                if sm:
                    inner = sm.group(1)
                    cols = [c.strip() for c in inner.split(",")]
                    group_cols: List[str] = []
                    for c in cols:
                        if not re.search(r"(?is)\b(count|sum|avg|max|min|distinct)\s*\(", c) and c != "*":
                            cm = re.match(r"(?is)([A-Za-z_][\w\.]*)", c)
                            if cm:
                                group_cols.append(cm.group(1))
                    if group_cols:
                        s = f"{s} GROUP BY {', '.join(group_cols)}"

        # ORDER BY guard (only add if not already present and an order word is hinted)
        if re.search(r"\b(order\s+by|sort|ascending|descending)\b", hint_lc):
            if not re.search(r"(?is)\border\s+by\b", s):
                sm = re.match(r"(?is)^\s*select\s+(?:distinct\s+)?([A-Za-z_][\w\.]*)", s)
                col = sm.group(1) if sm else "1"
                direction = "DESC" if re.search(r"\b(descending|desc)\b", hint_lc) else "ASC"
                s = f"{s} ORDER BY {col} {direction}"

        return s + ";"

    def _build_system_prompt(self, guard_instructions: List[str]) -> str:
        base = (
            "You are a Text-to-SQL generator. Produce exactly one syntactically valid "
            "SQL statement that answers the question against the provided schema. "
            "Return only the SQL, with no prose and no markdown fences."
        )
        if not guard_instructions:
            return base
        guards_text = "\n".join(f"- {g}" for g in guard_instructions)
        return (
            base
            + "\n\nHARD CONSTRAINTS (these are non-negotiable; the SQL MUST satisfy them):\n"
            + guards_text
        )

    def _build_user_prompt(self, body: str, hint: str, guard_instructions: List[str]) -> str:
        parts = [f"Schema:\n{self.schema}", f"Question: {body}"]
        if hint:
            parts.append(f"Hint: {hint}")
        if guard_instructions:
            parts.append(
                "You MUST encode the following hint-derived requirements in the SQL:\n"
                + "\n".join(f"- {g}" for g in guard_instructions)
            )
        return "\n\n".join(parts)

    def solve(self, question: str) -> str:
        body, hint = self._extract_hint(question)
        guard_instructions = self._activated_guards(hint)

        system_prompt = self._build_system_prompt(guard_instructions)
        user_prompt = self._build_user_prompt(body, hint, guard_instructions)

        raw = self.llm(user_prompt, system=system_prompt, temperature=0.0, n=1)
        sql = bridge.extract_sql(raw)

        if not sql:
            return ""

        # Strategy: programmatically enforce guards in control flow (not just in prompt).
        enforced = self._enforce_guards(sql, hint)

        # Optional sanity check: if execution is enabled and SQL runs, return enforced.
        # We still return enforced even if execution fails, because hints are mandatory.
        _ = self.execute(enforced)

        return enforced