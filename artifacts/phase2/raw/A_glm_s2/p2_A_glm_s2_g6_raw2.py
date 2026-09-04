"""Greedy SQL draft, then up to three regeneration rounds where the actual database error message is fed back to the frozen solver for repair."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

_MAX_REPAIRS = 3

_SYSTEM = (
    "You are a careful SQL expert working with SQLite. Given a database "
    "schema and a question, write exactly one SQL query that answers the "
    "question using only tables and columns that appear in the schema. "
    "Reply with a single SQL statement inside a