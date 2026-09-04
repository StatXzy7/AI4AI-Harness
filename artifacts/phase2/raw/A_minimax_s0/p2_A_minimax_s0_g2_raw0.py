"""Two-stage harness: first LLM plans a schema sketch, second LLM writes SQL conditioned on it."""
# MECHANISM: twostage
from ..harness_base import SQLHarness
from .. import bridge


PLAN_SYSTEM = (
    "You are a database planning assistant. Given a natural language question and a SQL schema, "
    "produce a concise plan describing: (1) which tables/columns are needed, (2) relevant joins, "
    "(3) filtering conditions, (4) aggregations. Output ONLY the plan, no SQL."
)

SQL_SYSTEM = (
    "You are a SQL expert. Given a natural language question, a schema, and a plan, "
    "produce a single valid SQL query that answers the question. "
    "Output ONLY the SQL query, nothing else. Wrap it in