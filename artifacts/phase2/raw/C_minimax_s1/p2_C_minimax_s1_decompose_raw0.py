"""Decomposes a natural-language question into ordered sub-questions, answers each via small LLM calls, then assembles the final SQL."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_DECOMPOSE_SYSTEM = (
    "You are a query planner for text-to-SQL. You decompose a user's natural-language "
    "question into an ordered list of focused sub-questions that, when answered, allow "
    "construction of a single correct SQL query against the given database schema."
)

_DECOMPOSE_USER = """Given the database schema below, decompose the user's question into an
ordered JSON list of sub-questions. Each sub-question should address one logical
piece of the query (tables/joins, filters, aggregations, ordering, etc.).

Output STRICTLY a JSON object of the form:
{{"steps": [{{"id": 1, "goal": "...", "focus": "tables|joins|filters|columns|aggregation|order|limit|expressions"}}, ...]}}

Schema:
{schema}

Question:
{question}

JSON:
"""

_SUB_SYSTEM = (
    "You are a SQL sub-query planner. Given a schema and a single sub-question, "
    "you produce a concise *plan fragment* (not SQL yet) describing exactly what "
    "that sub-question contributes to the final query."
)

_SUB_USER = """Schema:
{schema}

Original question:
{question}

Sub-question #{idx}: {goal}
Focus: {focus}

Earlier steps (already answered):
{earlier}

Respond as compact JSON:
{{"fragment": "...", "tables": ["..."], "columns": ["..."], "notes": "..."}}
JSON:
"""

_ASSEMBLE_SYSTEM = (
    "You are a SQL assembly expert. Given a database schema and a sequence of "
    "plan fragments, you produce ONE final SQLite-compatible SQL query."
)

_ASSEMBLE_USER = """Schema:
{schema}

Original question:
{question}

Plan fragments (in order):
{fragments}

Assemble the single best SQL query that answers the original question.
Return ONLY the SQL (no markdown, no commentary). If a SELECT requires no FROM,
use a literal SELECT. Use standard SQLite syntax.

SQL:
"""

_REPAIR_SYSTEM = (
    "You are a SQL repair assistant. You receive a SQL query that produced an "
    "error, the error message, the schema, and the original question. You return "
    "a corrected SQL query that avoids the error."
)

_REPAIR_USER = """Schema:
{schema}

Original question:
{question}

Failed SQL:
{sql}

Error:
{error}

Return a corrected SQL query. Output ONLY the SQL.

SQL:
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json(text: str) -> Optional[Any]:
    """Best-effort JSON object extraction from an LLM response."""
    if text is None:
        return None
    s = text.strip()

    # Strip markdown fences if present
    if s.startswith("