"""Wraps a frozen weak solver by enforcing strict SQL fence formatting and post-extraction schema/structure validation before returning the final query."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2FormatGuard(SQLHarness):
    def solve(self, question: str) -> str:
        # ------------------------------------------------------------------
        # STRATEGY:
        #   Stage 1: Prompt the weak solver with a heavy format-emphasis
        #            system prompt requiring a