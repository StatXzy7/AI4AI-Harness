"""Text-to-SQL harness that repairs its own SQL: it executes each generated query and feeds the execution error back to the LLM for regeneration until the query runs or the attempt budget is spent."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS1G7(SQLHarness):
    """Repair-loop harness: generate SQL, execute it, feed execution errors
    back into the prompt, and regenerate, up to a bounded number of attempts."""

    MAX_ATTEMPTS = 4

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL engine. Given a database schema and a "
        "natural-language question, write one syntactically valid SQL query "
        "that answers the question. Output only the SQL query (a