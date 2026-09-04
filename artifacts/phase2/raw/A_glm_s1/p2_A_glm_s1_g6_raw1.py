"""Repair harness: generate one SQL query greedily, execute it, and feed the verbatim engine error back to the frozen solver for up to three corrective regenerations."""

# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G6(SQLHarness):
    """Wrap the frozen weak solver in an execution-feedback repair loop.

    Control flow of ``solve`` (a real loop, not just a longer prompt):

    1. One greedy LLM call (temperature 0.0, n=1) produces a candidate query,
       extracted from the reply with ``bridge.extract_sql``.
    2. The candidate is executed against the database via ``self.execute``.
    3. If execution succeeds, the query is returned immediately.
    4. If execution fails -- engine error, or no SQL could be extracted at
       all -- the failing query and its verbatim error message are folded
       back into the prompt, and the frozen solver regenerates a corrected
       query.  The whole failure history is carried along, so later rounds
       see every mistake, not just the most recent one.
    5. Steps 2-4 repeat for at most ``MAX_REPAIRS`` repair rounds.  The loop
       also stops early when the frozen model repeats a query that already
       failed, since identical prompts deterministically reproduce it.
    6. If no candidate ever executes cleanly, the last non-empty candidate
       is returned (``""`` only if the solver never emitted a query).
    """

    MAX_REPAIRS = 3

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. "
        "Reply with exactly one SQL query inside a