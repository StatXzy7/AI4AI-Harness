"""Generate SQL with the frozen solver, execute it against the database, and on failure regenerate up to 2 times while feeding the exact SQLite error back to the model."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS0Repair(SQLHarness):
    """Text-to-SQL harness: one-shot generation followed by an execution-checked
    self-repair loop with at most MAX_REPAIRS regeneration rounds."""

    MAX_REPAIRS = 2

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL translator for SQLite. Given a database "
        "schema and a natural-language question, output a single valid SQLite "
        "query. Output only the SQL inside a