"""Wraps a frozen weak text-to-SQL solver with an explicit schema-linking pass that first identifies mentioned tables/columns and then writes SQL against that linked subset."""
from __future__ import annotations

import json
import re
from typing import Any

from ..harness_base import SQLHarness
from .. import bridge


# Default prompts (overridable via instance attributes if desired).
_SCHEMA_LINK_SYSTEM = (
    "You are a precise schema-linking assistant. Given a natural language question "
    "and a database schema, you identify the minimal subset of tables and columns "
    "that are required to answer the question. You only output valid JSON."
)

_SCHEMA_LINK_INSTRUCTIONS = (
    "Identify every table and every column that is needed (directly or indirectly) "
    "to answer the question. Be conservative: only include columns that genuinely "
    "contribute to selecting, filtering, joining, or aggregating the answer. "
    "Respond with JSON of the form:\n"
    "{\"tables\": [{\"name\": \"table_name\", \"columns\": [\"col1\", \"col2\"]}], ...}\n"
    "Do not include explanations or any text outside the JSON."
)

_SQL_SYSTEM = (
    "You are a precise text-to-SQL generator. You write a single SQLite-compatible "
    "SQL query that answers the question using only the provided linked schema subset."
)

_SQL_INSTRUCTIONS = (
    "Using ONLY the tables and columns listed in the linked schema subset below, "
    "write ONE SQL query that answers the question. "
    "Rules:\n"
    "  - Use only the listed tables and columns.\n"
    "  - Do not invent tables, columns, or values.\n"
    "  - Use JOINs with explicit ON clauses when combining tables.\n"
    "  - Prefer GROUP BY / aggregations when the question asks for counts, sums, averages, etc.\n"
    "  - Return only the SQL inside a single