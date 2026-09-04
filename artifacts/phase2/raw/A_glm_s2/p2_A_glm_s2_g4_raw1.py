"""Greedy text-to-SQL generation wrapped in an execution-feedback repair loop that replays database error messages back to the frozen solver for up to three corrective regeneration rounds."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2AGlmS2G4"]


class P2P2AGlmS2G4(SQLHarness):
    """Generate SQL greedily, execute it, then repair it from execution errors.

    Control flow (a genuine change from a single greedy call):

    1. One greedy call to the frozen solver produces a candidate query.
    2. The candidate is executed against the target database.
    3. If execution fails, the offending query plus the verbatim database
       error are fed back to the solver for a corrective regeneration.
    4. Steps 2-3 repeat for at most ``MAX_REPAIR_ROUNDS`` rounds, stopping
       early if the solver starts repeating itself.
    5. The first query that executes cleanly is returned; if every attempt
       fails, the most recent (most feedback-informed) attempt is returned.
    """

    MAX_REPAIR_ROUNDS = 3

    SYSTEM_PROMPT = (
        "You are a careful text-to-SQL translator. Using only the tables and "
        "columns shown in the provided schema, write exactly one SQL SELECT "
        "statement that answers the user's question. Reply with a single "
        "