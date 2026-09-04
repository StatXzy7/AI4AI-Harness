"""P2P2DMinimaxS2FormatGuard wraps a frozen weak Text-to-SQL solver with strict output formatting and schema-fidelity guardrails."""
from ..harness_base import SQLHarness
from .. import bridge
import re


class P2P2DMinimaxS2FormatGuard(SQLHarness):
    # Strict system prompt enforcing format and schema adherence
    SYSTEM_PROMPT = (
        "You are a precise Text-to-SQL generator. "
        "Your ONLY task is to convert the user's natural language question into a single valid SQL query "
        "that runs against the provided database schema.\n\n"
        "STRICT RULES:\n"
        "1. Use ONLY tables, columns, and identifiers that appear in the provided schema. Do NOT invent or guess any names.\n"
        "2. Match the exact casing and naming convention shown in the schema (table and column names).\n"
        "3. Output MUST be wrapped in a single