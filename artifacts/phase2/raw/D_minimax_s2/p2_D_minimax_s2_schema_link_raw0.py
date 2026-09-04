"""Two-pass harness: first link schema elements from the question, then generate SQL against the linked subset."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2SchemaLink(SQLHarness):
    """Pass-1 schema linker + Pass-2 SQL generator with self-repair fallback.

    Pass 1: ask the LLM to enumerate only the tables/columns it needs.
    Pass 2: ask the LLM to produce SQL using only the linked schema elements.
    If execution fails, a repair pass uses the error message to revise the SQL.
    """

    # ---------- Pass 1: schema linking ----------
    _LINKER_SYSTEM = (
        "You are a precise schema linker for a Text-to-SQL system. "
        "You do NOT write SQL. You only identify which tables and columns "
        "from the provided schema are required to answer the question."
    )

    _LINKER_INSTRUCTIONS = """\
Given the database schema below and a natural-language question, list ONLY
the tables and columns that are needed to answer the question.

Output strict JSON of the form:
{"tables": ["<table1>", "<table2>", ...],
 "columns": [{"table": "<table>", "column": "<col>"}, ...],
 "reasoning": "<one short sentence>"}

Rules:
- Use the exact identifiers from the CREATE TABLE statements (preserve case).
- Include join keys and any column used in WHERE / SELECT / GROUP BY / ORDER BY.
- Do not invent columns or tables that are not in the schema.
- If no schema element is needed, return empty lists.

SCHEMA:
{schema}

QUESTION:
{question}

JSON:"""

    # ---------- Pass 2: SQL generation over the linked subset ----------
    _SQL_SYSTEM = (
        "You are a precise Text-to-SQL generator. You write a single SQLite-compatible "
        "SELECT statement that answers the question using only the linked schema elements "
        "provided. Output the SQL inside a fenced