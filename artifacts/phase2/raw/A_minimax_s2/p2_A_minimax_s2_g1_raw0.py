# MECHANISM: repair
"""Wraps a weak solver with a SQL execution repair loop that feeds errors back to the LLM."""
from ..harness_base import SQLHarness
from .. import bridge


REPAIR_SYSTEM = (
    "You are a SQL repair assistant. The previous SQL query failed to execute. "
    "You will be shown the database schema, the original question, the SQL that was generated, "
    "and the execution error returned by the database engine. Your job is to produce a corrected "
    "SQL query that fixes the error while still answering the original question. "
    "Respond ONLY with the corrected SQL query, with no prose, no markdown fences, and no explanation."
)

REPAIR_PROMPT_TEMPLATE = (
    "SCHEMA:\n{schema}\n\n"
    "ORIGINAL QUESTION:\n{question}\n\n"
    "PREVIOUS SQL:\n{prev_sql}\n\n"
    "EXECUTION ERROR:\n{error}\n\n"
    "Provide the corrected SQL query."
)


def _strip_code_fence(text: str) -> str:
    """Remove markdown code fences if the LLM wrapped the SQL in them."""
    raw = text.strip()
    if raw.startswith("