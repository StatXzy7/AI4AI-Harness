"""P2P2AMinimaxS0G6: uses a twostage mechanism where schema linking is performed first and the resulting artifact guides SQL generation."""
# MECHANISM: twostage
import json
import re
from ..harness_base import SQLHarness
from .. import bridge


SCHEMA_LINKING_SYSTEM = (
    "You are a precise schema linker'skeleton extractor. Given a natural language question "
    "and a database schema, your job is to identify the minimal set of schema elements "
    "needed to answer the question. Output ONLY valid JSON with this structure:\n"
    "{\n"
    '  "tables": [{"name": "table_name", "reason": "why this table is needed"}],\n'
    '  "columns": [{"table": "table_name", "name": "column_name", "reason": "why needed"}],\n'
    '  "conditions": ["col op value", ...],\n'
    '  "joins": [{"left": "t1.c1", "right": "t2.c2"}],\n'
    '  "intent": "concise description of what the query is asking"\n'
    "}\n"
    "Be conservative; only include schema elements that are clearly required. No prose."
)


GENERATION_SYSTEM = (
    "You are an expert SQL generator. Given a natural language question, a database schema, "
    "and a schema linking analysis, produce a single SQLite-compatible SQL query that answers "
    "the question.\n"
    "Rules:\n"
    "- Use ONLY tables and columns listed in the schema linking section; ignore any others.\n"
    "- Prefer explicit JOINs using the join hints provided.\n"
    "- Respect the identified WHERE conditions.\n"
    "- Output ONLY the SQL statement. No markdown fences, no commentary."
)


REPAIR_SYSTEM = (
    "You are an expert SQL debugger. The previous SQL query failed to execute. "
    "Given the original question, the schema, the schema linking, the failing SQL, and the "
    "execution error message, produce a corrected SQL query that should run on SQLite.\n"
    "Rules:\n"
    "- Carefully read the error and fix the syntax or semantic issue.\n"
    "- Preserve the original intent of the query.\n"
    "- Output ONLY the corrected SQL statement. No markdown fences, no commentary."
)


_FENCE_RE = re.compile(r"