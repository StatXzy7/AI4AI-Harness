"""Select the final SQL by majority vote over multiple sampled completions from the frozen solver, restricted to candidates that execute without error whenever at least one does."""

# MECHANISM: vote

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2BGlmS1G1"]


class P2P2BGlmS1G1(SQLHarness):
    """Execution-validated majority voting over sampled SQL candidates.

    Control flow per question:
      1. draw one greedy anchor completion (the frozen solver's own answer)
         plus a batch of temperature samples from the same prompt;
      2. extract SQL from every completion and canonicalize it (case,
         whitespace, backticks, trailing semicolons) so textual duplicates
         collapse into one candidate that accrues all their votes;
      3. execute each distinct candidate once and keep only the ones that run
         without error -- if none execute, draw a second hotter batch, and as
         a last resort open the vote to every candidate;
      4. return the executable candidate with the most votes, breaking ties
         by non-empty result sets and then by earliest sample order.

    Execution outcomes are used only to rank candidates; error text is never
    fed back into any prompt, so the solver itself stays frozen.
    """

    N_SAMPLES = 8            # temperature samples in the first batch
    SAMPLE_TEMPERATURE = 0.8
    TOPUP_SAMPLES = 8        # extra samples when nothing executes cleanly
    TOPUP_TEMPERATURE = 1.0
    MAX_DRAWS_PER_BATCH = 8  # llm calls per batch (backend may ignore n > 1)

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. Given a database schema and a "
        "natural-language question, write exactly one SQL query that answers "
        "the question."
    )

    def solve(self, question: str) -> str:
        question = question if isinstance(question, str) else str(question)
        self._exec_cache = {}
        prompt = self._build_prompt(question)

        # Batch 1: greedy anchor + diverse samples, all from the frozen solver.
        texts = self._draw(prompt, temperature=0.0