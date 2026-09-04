"""Wraps a frozen weak Text-to-SQL solver by extracting any 'Hint:' line and restating its constraints as hard guardrails before delegating to the LLM."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


# Phrases that signal a hard requirement inside the hint text.
_NUMERIC_PATTERNS = [
    re.compile(r"\b(?:top|limit|return|show|give\s+me|first)\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"\b(\d+)\s+(?:rows?|results?|records?|entries)\b", re.IGNORECASE),
    re.compile(r"\b(?:only|exactly|just)\s+(\d+)\b", re.IGNORECASE),
]

_SORT_HINTS = [
    (re.compile(r"\b(?:highest|top|max(?:imum)?|largest|biggest|most)\b", re.IGNORECASE), "DESC"),
    (re.compile(r"\b(?:lowest|bottom|min(?:imum)?|smallest|least)\b", re.IGNORECASE), "ASC"),
]

_ORDER_WORD_MAP = {
    "DESC": ["desc", "descending", "high-to-low", "high to low", "largest first", "highest first"],
    "ASC":  ["asc", "ascending", "low-to-high", "low to high", "smallest first", "lowest first"],
}

_NEGATIVE_TOKENS = re.compile(
    r"\b(?:not|never|don't|do\s+not|didn't|did\s+not|won't|will\s+not|would\s+not|"
    r"should\s+not|shouldn't|isn't|aren't|wasn't|weren't|except|excluding|exclude|"
    r"other\s+than|rather\s+than|instead\s+of|no\s+longer)\b",
    re.IGNORECASE,
)

_AGG_HINTS = [
    (re.compile(r"\b(?:total|sum|overall)\b", re.IGNORECASE), "SUM"),
    (re.compile(r"\b(?:average|avg|mean)\b", re.IGNORECASE), "AVG"),
    (re.compile(r"\b(?:count|number\s+of|how\s+many|num)\b", re.IGNORECASE), "COUNT"),
    (re.compile(r"\b(?:maximum|highest)\s+(?:value|amount|price|score|number)\b", re.IGNORECASE), "MAX"),
    (re.compile(r"\b(?:minimum|lowest)\s+(?:value|amount|price|score|number)\b", re.IGNORECASE), "MIN"),
]

_DISTINCT_HINTS = re.compile(
    r"\b(?:distinct|unique|deduplicate|dedup|without\s+duplicates?|no\s+duplicates?)\b",
    re.IGNORECASE,
)

_NULL_HINTS = re.compile(
    r"\b(?:is\s+null|null\s+values?|nulls|missing|absent|unknown\s+values?)\b",
    re.IGNORECASE,
)

_NOT_NULL_HINTS = re.compile(
    r"\b(?:is\s+not\s+null|not\s+null|non\s*-?\s*null|not\s+missing|present\s+values?)\b",
    re.IGNORECASE,
)


def _split_hint(question: str) -> Tuple[str, Optional[str]]:
    """Return (clean_question, hint_text_or_None)."""
    if not question:
        return "", None
    # Tolerate 'Hint -', 'Hint:', 'Hint :', and 'Hints:'.
    pattern = re.compile(r"^\s*Hint\s*[-:]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(question)
    if not match:
        return question.strip(), None
    hint_text = match.group(1).strip()
    cleaned = (question[: match.start()] + question[match.end():]).strip()
    # Collapse stray blank lines.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, hint_text


def _detect_limit(hint: str) -> Optional[str]:
    for pat in _NUMERIC_PATTERNS:
        m = pat.search(hint)
        if m:
            return m.group(1)
    return None


def _detect_order_direction(hint: str) -> Optional[str]:
    for pat, direction in _SORT_HINTS:
        if pat.search(hint):
            return direction
    # Explicit "ORDER BY ... DESC/ASC"-style hints.
    m = re.search(r"\border\s+by\s+[^,;]+\s+(asc|desc|ascending|descending)\b",
                  hint, re.IGNORECASE)
    if m:
        word = m.group(1).lower()
        return "DESC" if word.startswith("desc") else "ASC"
    for direction, words in _ORDER_WORD_MAP.items():
        for w in words:
            if re.search(r"\b" + re.escape(w) + r"\b", hint, re.IGNORECASE):
                return direction
    return None


def _detect_order_column(hint: str) -> Optional[str]:
    # Try "by <column>" first.
    m = re.search(r"\b(?:order|sort|rank)\s+by\s+([A-Za-z_][\w\.]*)", hint, re.IGNORECASE)
    if m:
        return m.group(1)
    # Fall back to "<adjective> <column>" patterns.
    m = re.search(
        r"\b(?:highest|top|max(?:imum)?|largest|biggest|most|lowest|bottom|min(?:imum)?|smallest|least)\s+"
        r"([A-Za-z_][\w\.]*)",
        hint, re.IGNORECASE,
    )
    if m:
        return m.group(1)
    return None


def _detect_negation(hint: str) -> bool:
    return bool(_NEGATIVE_TOKENS.search(hint))


def _detect_negated_column(hint: str) -> Optional[str]:
    """Try to identify a column referenced in a NOT/EXCLUDE clause."""
    # "not <col>", "exclude <col>", "no <col>".
    m = re.search(
        r"\b(?:not|exclude|excluding|except(?:ing)?|no)\s+([A-Za-z_][\w\.]*)",
        hint, re.IGNORECASE,
    )
    if m:
        return m.group(1)
    return None


def _detect_negated_value(hint: str) -> Optional[str]:
    patterns = [
        re.compile(r"\bnot\s+(?:equal\s+to\s+|=|:)?\s*[\'\"]?([\w\-]+)[\'\"]?", re.IGNORECASE),
        re.compile(r"\bnot\s+in\s+\(?\s*([\w\',\"\s]+)\s*\)?", re.IGNORECASE),
        re.compile(r"\bexclude\s+[\'\"]?([\w\-]+)[\'\"]?", re.IGNORECASE),
        re.compile(r"\bexcept\s+[\'\"]?([\w\-]+)[\'\"]?", re.IGNORECASE),
        re.compile(r"\bother\s+than\s+[\'\"]?([\w\-]+)[\'\"]?", re.IGNORECASE),
        re.compile(r"\binstead\s+of\s+[\'\"]?([\w\-]+)[\'\"]?", re.IGNORECASE),
    ]
    for pat in patterns:
        m = pat.search(hint)
        if m:
            return m.group(1).strip().strip(",\"'")
    return None


def _detect_aggregation(hint: str) -> Optional[str]:
    hits = []
    for pat, agg in _AGG_HINTS:
        if pat.search(hint):
            hits.append(agg)
    # Prefer COUNT if "how many" present; prefer SUM if "total".
    if "COUNT" in hits:
        return "COUNT"
    if hits:
        return hits[0]
    return None


def _detect_distinct(hint: str) -> bool:
    return bool(_DISTINCT_HINTS.search(hint))


def _detect_null_filter(hint: str) -> Optional[str]:
    """Return 'NULL', 'NOT NULL', or None."""
    if _NOT_NULL_HINTS.search(hint):
        return "NOT NULL"
    if _NULL_HINTS.search(hint):
        return "NULL"
    return None


def _detect_null_column(hint: str) -> Optional[str]:
    m = re.search(
        r"\b(?:where|for|in)\s+([A-Za-z_][\w\.]*)\s+is\s+(?:not\s+)?null\b",
        hint, re.IGNORECASE,
    )
    if m:
        return m.group(1)
    return None


def _detect_equality_value(hint: str) -> Optional[Tuple[Optional[str], str]]:
    """Pick up 'where col = value' style hints."""
    m = re.search(
        r"\bwhere\s+([A-Za-z_][\w\.]*)\s*=\s*[\'\"]?([\w\-]+)[\'\"]?",
        hint, re.IGNORECASE,
    )
    if m:
        return m.group(1), m.group(2)
    m = re.search(
        r"\b([A-Za-z_][\w\.]*)\s+is\s+[\'\"]?([\w\-]+)[\'\"]?",
        hint, re.IGNORECASE,
    )
    if m:
        return m.group(1), m.group(2)
    m = re.search(
        r"\bfor\s+([A-Za-z_][\w\.]*)\s*=?\s*[\'\"]?([\w\-]+)[\'\"]?",
        hint, re.IGNORECASE,
    )
    if m:
        return m.group(1), m.group(2)
    return None


def _extract_constraints(hint: str) -> List[str]:
    """Translate hint text into a list of hard requirement strings."""
    if not hint:
        return []

    rules: List[str] = []
    seen = set()

    def add(rule: str) -> None:
        key = rule.lower()
        if key not in seen:
            seen.add(key)
            rules.append(rule)

    limit = _detect_limit(hint)
    if limit:
        add(f"The query MUST return exactly {limit} rows; emit `LIMIT {limit}`.")

    direction = _detect_order_direction(hint)
    order_col = _detect_order_column(hint)
    if direction:
        if order_col:
            add(f"The query MUST order by `{order_col}` in {direction} order "
                f"(`ORDER BY {order_col} {direction}`).")
        else:
            add(f"The query MUST use `ORDER BY ... {direction}`.")

    agg = _detect_aggregation(hint)
    if agg:
        add(f"The query MUST aggregate using `{agg}`.")

    if _detect_distinct(hint):
        add("The query MUST use `SELECT DISTINCT`.")

    null_filter = _detect_null_filter(hint)
    null_col = _detect_null_column(hint)
    if null_filter == "NOT NULL":
        col_part = f"`{null_col}`" if null_col else "the relevant column"
        add(f"The query MUST filter with `{col_part} IS NOT NULL`.")
    elif null_filter == "NULL":
        col_part = f"`{null_col}`" if null_col else "the relevant column"
        add(f"The query MUST filter with `{col_part} IS NULL`.")

    eq = _detect_equality_value(hint)
    if eq:
        col, val = eq
        add(f"The query MUST filter with `{col} = '{val}'` (treat as an equality constraint).")

    if _detect_negation(hint):
        neg_col = _detect_negated_column(hint)
        neg_val = _detect_negated_value(hint)
        if neg_col and neg_val:
            add(f"The query MUST exclude rows where `{neg_col}` is '{neg_val}' "
                f"(use `{neg_col} <> '{neg_val}'` or `NOT ({neg_col} = '{neg_val}')`).")
        elif neg_col:
            add(f"The query MUST exclude or negate the `{neg_col}` condition.")
        elif neg_val:
            add(f"The query MUST exclude the value '{neg_val}'.")
        else:
            add("The query MUST apply a negation / exclusion clause.")

    return rules


def _build_system_prompt(constraints: List[str]) -> str:
    if not constraints:
        return ""
    joined = "\n".join(f"- {c}" for c in constraints)
    return (
        "You are a precise Text-to-SQL generator. The user question contains a "
        "Hint line describing HARD requirements. The following rules are NOT "
        "suggestions — they are mandatory and your SQL MUST satisfy every one "
        "of them. If a rule conflicts with your prior inference, the rule wins.\n"
        "Hard requirements:\n"
        f"{joined}\n"
        "Return ONLY a single SQL statement, no prose, no markdown fences."
    )


def _extract_first_sql(text: str) -> Optional[str]:
    if not text:
        return None
    sql = bridge.extract_sql(text)
    if sql:
        sql = sql.strip()
        if sql:
            return sql
    # Fallback: pick up the first SELECT/CREATE/INSERT/UPDATE/DELETE/WITH block.
    m = re.search(
        r"(?: