"""Generate SQL, execute it via SQLite, and on failure regenerate up to 2 times using the exact error message as feedback."""
from __future__ import annotations

from ..harness_base import SQLHarness
from .. import bridge


SYSTEM_PROMPT = (
    "You are an expert Text-to-SQL generator. Given a question and a database schema, "
    "produce a SINGLE SQLite-compatible SQL query that answers the question. "
    "Return ONLY the SQL inside a