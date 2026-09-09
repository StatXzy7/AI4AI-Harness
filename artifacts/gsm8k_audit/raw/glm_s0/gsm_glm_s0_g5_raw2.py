"""Greedy-anchored self-consistency with disagreement-triggered adjudication: solve once greedily plus K temperature-sampled chains, majority-vote the numeric answers extracted from every chain, and, whenever the vote is split or clashes with the greedy anchor, run a final temperature-0 adjudication pass that re-solves the problem with the candidate answers in view."""

import re
from collections import Counter

from ..harness_base import MathHarness

__all__ = ["GsmGsmGlmS0G5"]


class GsmGsmGlmS0G5(MathHarness):
    """Multi-sample voting harness for grade-school math word problems.

    Control flow inside ``solve`` (a real change vs. one greedy call):

      1. One greedy (temperature 0) chain is generated as the *anchor*.
      2. ``K_SAMPLES`` additional chains are sampled at a higher temperature
         for diversity.
      3. A final numeric answer is extracted from every chain ("#### N",
         "the answer is N", or last number as a last resort) and normalized,
         then majority-voted.
      4. A clear consensus (>= STRONG_COUNT votes and >= VOTE_SHARE of the
         parsed votes), or a modest consensus that agrees with the greedy
         anchor, is returned immediately with no extra calls.
      5. Otherwise -- split vote, thin margin, or an anchor/majority clash --
         a single temperature-0 *adjudication* call re-solves the problem
         with the distinct candidate answers listed, and its verdict picks
         the winner (a brand-new number from the adjudicator is only trusted
         when the vote itself was too thin to mean anything).
      6. If no chain produced a parseable number at all, a bare
         "answer-only" fallback call is made.
    """

    # ---- decoding / voting configuration --------------------------------
    K_SAMPLES = 5            # sampled chains beyond the greedy anchor
    SAMPLE_TEMPERATURE = 0.7 # diversity for the sampled chains
    VOTE_SHARE = 0.5         # min fraction of parsed votes for a direct win
    STRONG_COUNT = 3         # votes that win even against a conflicting anchor
    MAX_CANDIDATES = 4