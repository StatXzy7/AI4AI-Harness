"""Self-consistency voting: sample several SQL candidates from the frozen solver, execute each distinct one, and return the query whose result set wins the sample-weighted majority vote."""
# MECHANISM: vote

from collections import Counter
from typing import Any, Dict, List, Tuple

from ..harness_base import SQLHarness
from .. import bridge

_SYSTEM = "You are an expert SQLite programmer. Reply with one SQL query only."


class P2P2BGlmS1G3(SQLHarness):
    """Executes a self-consistency (majority-vote) strategy over SQL candidates.

    Control flow, compared to a single greedy generation call:

      1. ``_draw_samples`` obtains ``NUM_SAMPLES`` candidate answers from the
         frozen solver at a non-zero temperature (one ``llm`` call with
         ``n=K`` when the backend honours it, topped up with individual calls
         otherwise).
      2. ``_collect_candidates`` extracts the SQL from every sample with
         ``bridge.extract_sql``, normalises the text, and deduplicates the
         candidates while recording how many raw samples backed each one.
      3. ``_execute_candidates`` runs each *distinct* candidate once through
         ``self.execute``.  Execution output is used purely to score and
         filter candidates for the vote -- errors are never fed back into a
         regeneration step.
      4. ``_vote`` groups the executable candidates by an order-insensitive
         fingerprint of their result sets, weights every group by the number
         of samples that produced it, and returns the strongest group's most
         frequently sampled query.
      5. If nothing executes, the vote falls back to the normalised SQL text;
         if sampling produced nothing extractable at all, one final greedy
         call at temperature 0 is made.
    """

    NUM_SAMPLES = 5
    SAMPLING_TEMPERATURE = 0.7
    MAX_SIGNATURE_ROWS = 1000

    PROMPT_TEMPLATE = (
        "Database schema:\n"
        "{schema}\n\n"
        "Write exactly one SQL query that answers the question below.\n"
        "Rules:\n"
        "- The query must be valid SQLite.\n"
        "- Use only tables and columns that appear in the schema.\n"
        "- Output the query in a single