"""P2P2D harness that parses Hint: constraints and enforces them as hard guards before/after weak-solver SQL generation."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


# Tokens / patterns used to extract constraints from the Hint: line.
_AGGREGATE_TOKENS = {
    "count": ["count", "number of", "how many"],
    "sum": ["sum", "total"],
    "avg": ["average", "avg", "mean"],
    "max": ["max", "maximum", "highest", "largest"],
    "min": ["min", "minimum", "lowest", "smallest"],
}
_LIMIT_RE = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)
_DISTINCT_RE = re.compile(r"\bdistinct\b", re.IGNORECASE)
_ORDER_ASC_RE = re.compile(r"\b(ascending|asc|lowest to highest|smallest to largest)\b", re.IGNORECASE)
_ORDER_DESC_RE = re.compile(r"\b(descending|desc|highest to lowest|largest to smallest)\b", re.IGNORECASE)
_TOP_RE = re.compile(r"\btop\s+(\d+)\b", re.IGNORECASE)


def _parse_hint(hint: str) -> Dict[str, Any]:
    """Extract structured constraints from the raw Hint: text."""
    h = (hint or "").strip()
    low = h.lower()

    constraints: Dict[str, Any] = {
        "raw": h,
        "aggregates": [],        # e.g. ["count", "sum"]
        "limit": None,           # int or None
        "distinct": False,
        "order": None,           # "ASC" | "DESC" | None
        "order_col_hint": None,  # free-text column hint if mentioned
        "top_n": None,           # int or None  (e.g. "top 3")
        "must_mention": [],      # phrases that MUST appear in the SQL
        "forbidden": [],         # phrases that must NOT appear in the SQL
    }

    # Aggregates
    for canon, variants in _AGGREGATE_TOKENS.items():
        for v in variants:
            if re.search(rf"\b{re.escape(v)}\b", low):
                constraints["aggregates"].append(canon)
                break

    # LIMIT / TOP
    if (m := _LIMIT_RE.search(h)):
        constraints["limit"] = int(m.group(1))
    if (m := _TOP_RE.search(h)):
        constraints["top_n"] = int(m.group(1))

    # DISTINCT
    if _DISTINCT_RE.search(h):
        constraints["distinct"] = True

    # Order direction
    if _ORDER_ASC_RE.search(h):
        constraints["order"] = "ASC"
    elif _ORDER_DESC_RE.search(h):
        constraints["order"] = "DESC"

    return constraints


def _split_hint_from_question(question: str) -> Tuple[str, str]:
    """Return (preamble, hint_text). Hint is the text after the first 'Hint:' marker."""
    if not question:
        return "", ""
    idx = question.find("Hint:")
    if idx == -1:
        return question, ""
    return question[:idx].strip(), question[idx + len("Hint:"):].strip()


def _constraints_to_guard_prompt(constraints: Dict[str, Any]) -> str:
    """Render extracted constraints as a HARD REQUIREMENTS block for the weak solver."""
    if not constraints or not constraints.get("raw"):
        return ""
    lines: List[str] = ["HARD REQUIREMENTS (MUST be satisfied in the generated SQL):"]
    aggs = constraints.get("aggregates") or []
    if aggs:
        lines.append(f"- Use aggregate(s): {', '.join(aggs).upper()}.")
    if constraints.get("distinct"):
        lines.append("- Use SELECT DISTINCT (deduplicate rows).")
    if constraints.get("limit") is not None:
        lines.append(f"- Include LIMIT {constraints['limit']}.")
    if constraints.get("top_n") is not None:
        lines.append(f"- Restrict to top {constraints['top_n']} rows (use ORDER BY ... LIMIT n).")
    if constraints.get("order"):
        lines.append(f"- Order results {constraints['order']}.")
    if not aggs and constraints["limit"] is None and constraints["top_n"] is None \
            and not constraints["distinct"] and constraints["order"] is None:
        lines.append("- Follow the hint's intent exactly; do not ignore it.")
    return "\n".join(lines)


def _sql_has(sql: str, needle: str) -> bool:
    return needle.lower() in (sql or "").lower()


def _apply_post_guards(sql: str, constraints: Dict[str, Any]) -> str:
    """Post-process the SQL so that HARD REQUIREMENTS are actually present."""
    if not sql or not constraints:
        return sql

    out = sql.rstrip().rstrip(";").strip()

    # DISTINCT
    if constraints.get("distinct"):
        if not re.search(r"\bselect\s+distinct\b", out, re.IGNORECASE):
            out = re.sub(r"\bselect\b", "SELECT DISTINCT", out, count=1, flags=re.IGNORECASE)

    # Aggregates: ensure at least one aggregate function appears.
    for agg in constraints.get("aggregates") or []:
        if not re.search(rf"\b{agg}\s*\(", out, re.IGNORECASE):
            # Insert a COUNT(*) projection if none of the requested aggregates exist.
            # This is a conservative fallback so the SQL still expresses the hint.
            if re.search(r"\bselect\s+\*\b", out, re.IGNORECASE):
                out = re.sub(r"\bselect\s+\*\b", f"SELECT {agg.upper()}(*)", out, count=1, flags=re.IGNORECASE)
            else:
                # Append the aggregate as an extra projection column.
                out = re.sub(r"\bselect\b", f"SELECT {agg.upper()}(*), ", out, count=1, flags=re.IGNORECASE)

    # ORDER BY direction
    if constraints.get("order") and re.search(r"\border\s+by\b", out, re.IGNORECASE):
        # Normalize trailing ASC/DESC to the requested direction.
        if constraints["order"] == "DESC":
            out = re.sub(r"\b(asc|ascending)\b", "DESC", out, flags=re.IGNORECASE)
            if not re.search(r"\bdesc\b", out, re.IGNORECASE):
                out = re.sub(r"(\border\s+by\s+[^;]+)$", r"\1 DESC", out, flags=re.IGNORECASE)
        else:
            out = re.sub(r"\b(desc|descending)\b", "ASC", out, flags=re.IGNORECASE)
            if not re.search(r"\basc\b", out, re.IGNORECASE):
                out = re.sub(r"(\border\s+by\s+[^;]+)$", r"\1 ASC", out, flags=re.IGNORECASE)

    # LIMIT / TOP-N
    target_limit = constraints.get("limit")
    if constraints.get("top_n") is not None:
        target_limit = constraints["top_n"] if target_limit is None else min(target_limit, constraints["top_n"])

    if target_limit is not None:
        if not re.search(r"\blimit\b", out, re.IGNORECASE):
            out = f"{out} LIMIT {target_limit}"

    return out


class P2P2DMinimaxS1HintGuard(SQLHarness):
    """
    Pipeline:
      1. Split question into preamble + Hint: text.
      2. Parse the hint into structured constraints (aggregates, distinct, limit, order).
      3. Render those constraints as a HARD REQUIREMENTS block prepended to the prompt.
      4. Call the frozen weak solver once.
      5. Post-process the returned SQL so the hard requirements are actually present
         (DISTINCT, aggregates, ORDER BY direction, LIMIT).
      6. Smoke-test the SQL via self.execute; on failure retry with an even stricter
         reformulation that explicitly lists the SQL fragments required.
    """

    # ---- internal helpers -------------------------------------------------

    @staticmethod
    def _split(question: str) -> Tuple[str, str]:
        return _split_hint_from_question(question)

    @staticmethod
    def _parse(hint: str) -> Dict[str, Any]:
        return _parse_hint(hint)

    @staticmethod
    def _render_guards(constraints: Dict[str, Any]) -> str:
        return _constraints_to_guard_prompt(constraints)

    @staticmethod
    def _post_guard(sql: str, constraints: Dict[str, Any]) -> str:
        return _apply_post_guards(sql, constraints)

    def _ask(self, prompt: str, system: str = "") -> str:
        # Thin wrapper so the retry logic stays readable.
        return self.llm(prompt, system=system, temperature=0.0, n=1)

    def _extract(self, text: str) -> str:
        sql = bridge.extract_sql(text) or ""
        return sql.strip()

    # ---- public API -------------------------------------------------------

    def solve(self, question: str) -> str:
        # 1) Split
        preamble, hint_text = self._split(question)
        if not preamble and not hint_text:
            preamble = question

        # 2) Parse constraints
        constraints = self._parse(hint_text)

        # 3) Build the guarded prompt
        guard_block = self._render_guards(constraints)

        system_prompt = (
            "You are a Text-to-SQL generator. Produce a single SQLite-compatible SQL "
            "statement that answers the user's question against the provided schema. "
            "You MUST satisfy every HARD REQUIREMENT listed in the prompt."
        )

        user_prompt_parts: List[str] = []
        if self.schema:
            user_prompt_parts.append(f"SCHEMA:\n{self.schema}")
        user_prompt_parts.append(f"QUESTION:\n{preamble}")
        if hint_text:
            user_prompt_parts.append(f"HINT: {hint_text}")
        if guard_block:
            user_prompt_parts.append(guard_block)
        user_prompt_parts.append("Return only the SQL statement, nothing else.")
        user_prompt = "\n\n".join(user_prompt_parts)

        # 4) First attempt
        raw = self._ask(user_prompt, system=system_prompt)
        sql = self._extract(raw)

        # 5) Post-guard the SQL so hint constraints are actually present
        sql = self._post_guard(sql, constraints)

        # 6) Smoke-test; on failure retry once with an even more explicit formulation
        if sql:
            verdict = self.execute(sql)
            if not verdict.get("ok", False):
                retry_parts = list(user_prompt_parts)
                retry_parts.append(
                    "STRICT MODE: The previous SQL failed to execute. Rewrite it so that "
                    "every HARD REQUIREMENT above is literally present in the SQL text. "
                    "Do not add explanations."
                )
                retry_prompt = "\n\n".join(retry_parts)
                raw2 = self._ask(retry_prompt, system=system_prompt)
                sql2 = self._extract(raw2)
                sql2 = self._post_guard(sql2, constraints)
                if sql2:
                    verdict2 = self.execute(sql2)
                    if verdict2.get("ok", False):
                        sql = sql2
                    # else keep the post-guarded first attempt; it at least reflects the hint.

        if not sql:
            # Last-resort: echo a minimal valid SQL so the harness always returns a string.
            sql = "SELECT 1;"

        return sql if sql.strip().endswith(";") else sql + ";"