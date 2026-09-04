"""Execution-aware self-consistency voting: sample several SQL candidates, execute each against the database, and return the candidate whose result is backed by the largest cluster of agreeing samples."""
# MECHANISM: vote

import json

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G3(SQLHarness):
    """Weak-solver wrapper that improves on a single greedy call by voting.

    Control flow (a real change vs. one greedy generation):

      1. An anchor candidate is generated greedily (temperature 0).
      2. A pool of K additional candidates is sampled at temperature > 0.
      3. Every distinct candidate is executed against the database.
      4. Executable candidates are clustered by an order-insensitive
         fingerprint of their result set; each cluster's score is the total
         number of pool proposals that produced it.  The strongest
         cluster's most-proposed member is returned.
      5. If nothing executes, a plain text-level majority vote decides.

    Execution is used only to score and select among the sampled
    candidates; error text is never fed back into any prompt.
    """

    K_SAMPLES = 8          # diverse candidates drawn for the vote pool
    SAMPLE_TEMP = 0.7      # temperature used for the vote pool
    MAX_EXECUTIONS = 8     # distinct candidates actually executed
    SIG_ROW_CAP = 500      # rows used when fingerprinting a result set

    SYSTEM = (
        "You are a precise Text-to-SQL engine. Answer with exactly one "
        "SQLite SELECT query and nothing else."
    )
    PROMPT_TEMPLATE = (
        "You are an expert SQLite programmer. Using only the schema below, "
        "write exactly one SQL query that answers the question.\n\n"
        "Schema:\n{schema}\n\n"
        "Question: {question}\n\n"
        "Output exactly one SQL query inside a