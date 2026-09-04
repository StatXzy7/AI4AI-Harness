"""Two-stage harness: schema-link the question to a pruned table/column subset (LLM vote + lexical vote, expanded with keys and FK join paths), then generate and execution-repair SQL against only that linked subset."""

from __future__ import annotations

import ast
import json
import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS2SchemaLink(SQLHarness):
    """Schema-link first (control-flow stage 1), then write/repair SQL against the linked subset (stage 2)."""

    MAX_REPAIR_ROUNDS = 2
    FALLBACK_REPAIR_ROUNDS = 1

    _TABLE_STOP_TOKENS = frozenset({"id"})
    _COLUMN_STOP_TOKENS = frozenset({
        "id", "name", "type", "code", "number", "no", "num", "date", "time",
        "year", "value", "count", "amount", "total", "description", "status",
        "text", "key",
    })
    _CONSTRAINT_WORDS = frozenset({
        "primary", "foreign", "unique", "key", "constraint", "check", "index",
        "create", "table", "references",
    })

    _CREATE_RE = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`\[]?([A-Za-z_][\w$]*)"
        r"[\"`\]]?\s*\((.*?)\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    _TEXT_TABLE_RE = re.compile(
        r"^\s*#?\s*Table[:\s]+([A-Za-z_][\w$]*)\s*,?\s*columns\s*=\s*\[([^\]]*)\]",
        re.IGNORECASE | re.MULTILINE,
    )
    _PAREN_LINE_RE = re.compile(
        r"^\s*[\"`]?([A-Za-z_][\w$]*)[\"`]?\s*\(([^()]*)\)\s*;?\s*$",
        re.MULTILINE,
    )
    _FK_RE = re.compile(
        r"FOREIGN\s+KEY\s*\(\s*[\"`\[]?([\w$]+)[\"`\]]?\s*\)\s*REFERENCES\s+"
        r"[\"`\[]?([\w$]+)[\"`\]]?\s*\(\s*[\"`\[]?([\w$]+)[\"`\]]?\s*\)",
        re.IGNORECASE,
    )
    _INLINE_REF_RE = re.compile(
        r"^\s*[\"`\[]?([\w$]+)[\"`\]]?\s+[\w$]+(?:\s*\([^)]*\))?\s+REFERENCES\s+"
        r"[\"`\[]?([\w$]+)[\"`\]]?\s*\(\s*[\"`\[]?([\w$]+)[\"`\]]?\s*\)",
        re.IGNORECASE,
    )
    _EQ_RE = re.compile(
        r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b"
    )

    _LINK_SYSTEM = "You are a precise schema-linking component for Text-to-SQL."
    _LINK_TEMPLATE = (
        "Database schema:\n{schema}\n\n"
        "Question: {question}\n\n"
        "Identify exactly which tables and which columns are needed to answer the "
        "question. Respond with ONLY a JSON object of the form:\n"
        '{{"tables": ["table_a", ...], "columns": ["table_a.column_x", ...]}}'
    )
    _GEN_SYSTEM = "You are an expert Text-to-SQL engine that writes a single correct SQL query."
    _GEN_TEMPLATE = (
        "Database schema (use ONLY these tables and columns):\n{schema}\n\n"
        "Question: {question}\n\n"
        "Write one SQL query that answers the question. Use only the tables and "
        "columns listed above. Output the SQL query only, with no explanation."
    )
    _REPAIR_TEMPLATE = (
        "Database schema (use ONLY these tables and columns):\n{schema}\n\n"
        "Question: {question}\n\n"
        "The following SQL query failed:\n{sql}\n\n"