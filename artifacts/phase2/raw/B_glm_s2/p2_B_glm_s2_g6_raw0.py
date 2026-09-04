"""A greedy draft SQL is executed against the database and, whenever execution fails, the exact database error is fed back to the frozen solver for up to three repair rounds."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration

from ..harness_base import SQLHarness
from .. import bridge


def _extract_sql(text):
    """Pull the SQL out of a model response, tolerating extractor hiccups."""
    if isinstance(text, (list, tuple)):
        text = text[0] if text else ""
    try:
        return bridge.extract_sql(text)
    except Exception:
        return ""


class P2P2BGlmS2G6(SQLHarness):
    """Execution-feedback repair loop around a frozen text-to-SQL solver.

    Control flow per question (a real change from a single greedy call):

        round 1    LLM -> SQL -> execute()            return at once if it runs
        round k>1  LLM sees every failed query *and the exact database error
                   that killed it* -> corrected SQL -> execute() -> ...

    Safeguards folded into the loop:
      * a non-read-only query is never sent to the database; the rejection is
        reported back to the model as just another repairable error;
      * if the model returns no SQL or repeats an already-failed query, the
        next round samples at ESCAPE_TEMPERATURE so the loop can escape the
        greedy fixed point (temperature drops back to 0.0 whenever the model
        produces a genuinely new candidate).
    """

    MAX_ROUNDS = 3           # total LLM calls: one draft + up to two repairs
    ESCAPE_TEMPERATURE = 0.7

    _SYSTEM = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "natural-language question, write exactly one read-only SQLite SELECT "
        "query that answers it. Use only tables and columns that appear in the "
        "schema. Respond with the query inside a single