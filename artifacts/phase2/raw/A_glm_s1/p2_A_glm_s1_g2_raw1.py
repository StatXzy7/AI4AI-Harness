"""Execution-guided repair loop: greedily generate a candidate SQL query, execute it against the database, and feed the exact execution error back into the prompt for up to three corrective regeneration rounds."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G2(SQLHarness):
    """Greedy generation + iterative, error-conditioned repair.

    Per-question control flow:
      1. One greedy generation conditioned on the schema and the question.
      2. The candidate is statically validated (single SELECT-style statement,
         no extra statements) and then executed against the live database.
      3. On any failure, the broken SQL *and the exact DB error string* are
         appended to a repair prompt and the model regenerates. If the model
         repeats an identical known-bad query, the sampling temperature is
         escalated to break the loop; duplicate queries are never re-executed.
      4. The first candidate that executes cleanly wins. If every round fails,
         the most recent non-empty attempt is returned as a best effort.
    """

    MAX_ROUNDS = 4                     # 1 initial attempt + 3 repair rounds
    TEMPERATURE_LADDER = (0.0, 0.0, 0.3, 0.7)
    FALLBACK_SQL = "SELECT 1"
    mechanism = "repair"

    BASE_SYSTEM = (
        "You are an expert SQLite programmer. Translate the user's question into "
        "a single valid SQLite SELECT statement that uses only tables and columns "
        "appearing in the given schema. Answer with exactly one query inside a "
        "