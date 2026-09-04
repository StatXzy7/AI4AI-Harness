"""Consensus voting over the frozen solver: solve draws one greedy anchor plus several stochastic decodes of the same prompt, executes every distinct read-only candidate, and returns the SQL whose execution-result signature earns the most sample votes."""
# MECHANISM: vote

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2BGlmS0G5"]


class P2P2BGlmS0G5(SQLHarness):
    """Execution-grounded self-consistency voting over the frozen weak solver.

    Instead of trusting a single greedy generation, ``solve``:

      1. draws one greedy anchor decode (temperature 0) and ``N_SAMPLES``
         stochastic decodes of the *same* prompt from the frozen solver;
      2. deduplicates the extracted SQL candidates by a normalized form and
         counts how many generations produced each one;
      3. executes each distinct read-only candidate against the database;
      4. lets every generation cast one vote for