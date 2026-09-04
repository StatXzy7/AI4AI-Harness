"""Schema-linking harness: an LLM first selects the tables/columns mentioned by the question, the schema is programmatically pruned to that linked subset, and SQL is then generated (and execution-repaired) against only the subset."""

import json
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2SchemaLink(SQLHarness):
    """Two-stage pipeline:

    Stage 1 (schema linking): ask the LLM exactly which tables and columns the
    question refers to (including join/filter/group/order columns), then prune
    the schema down to that linked subset *in code*.

    Stage 2 (SQL writing): generate the query against only the linked subset,
    then validate it with the executor and repair on error (bounded retries,
    escalating to the full schema if the error suggests over-pruning).
    """

    MAX_REPAIRS = 2

    LINK_SYSTEM = (
        "You are Kimi, a precise schema-linking assistant for Text-to-SQL. "
        "Given a database schema and a question, identify exactly which tables "
        "and columns are needed to answer it, including columns used for "
        "joins, filtering, grouping, and ordering. Respond with JSON only."
    )

    GEN_SYSTEM = (
        "You are Kimi, an expert SQLite Text-to-SQL assistant. Given a "
        "database schema and a question, write one syntactically correct "
        "SQLite query that answers the question. Use only the tables and "
        "columns shown in the schema. Output only the SQL inside a