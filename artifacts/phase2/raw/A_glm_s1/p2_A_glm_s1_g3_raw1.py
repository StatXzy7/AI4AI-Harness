"""Execution-aware self-consistency voting: the harness generates one greedy plus several stochastic SQL candidates, executes every distinct candidate, and returns the valid candidate whose result set wins the most votes across samples."""

# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G3(SQLHarness):
    """Self-consistency voting over executed text-to-SQL samples.

    Control flow (a real change vs. a single greedy generation call):

      1. One greedy SQL candidate is generated at temperature 0.0.
      2. K-1 additional candidates are sampled at a non-zero temperature.
      3. Every distinct candidate (after normalization/dedup) is executed.
      4. Candidates that execute successfully each cast one vote for their
         result-set signature; the signature with the most votes wins, and
         the earliest candidate producing it (greedy candidate first) is
         returned. Result-set voting lets semantically different but
         equivalent SQL texts pool their support.
      5. If no candidate executes cleanly, the greedy candidate is returned
         as a safe fallback (no extra LLM round-trip, no error feedback).
    """

    TOTAL_SAMPLES = 5            # 1 greedy + 4 stochastic samples
    SAMPLE_TEMPERATURE = 0.8
    MAX_SIGNATURE_ROWS = 256     # cap on rows used for result fingerprinting

    SYSTEM = (
        "You are an expert text-to-SQL engine. You answer with a single "
        "SQLite query and nothing else."
    )

    def solve(self, question: str) -> str:
        candidates = self._collect_candidates(question)
        if not candidates:
            return ""
        scored = self._score_candidates(candidates)
        return self._vote(scored)

    # ------------------------------------------------------------------
    # candidate generation
    # ------------------------------------------------------------------
    def _collect_candidates(self, question):
        prompt = self._build_prompt(question)
        candidates = []

        # 1) greedy anchor candidate
        greedy = self._sample(prompt, 0.0)
        if greedy:
            candidates.append(greedy)

        # 2) stochastic samples for the vote
        for _ in range(self.TOTAL_SAMPLES - 1):
            sql = self._sample(prompt, self.SAMPLE_TEMPERATURE)
            if sql:
                candidates.append(sql)

        return self._dedupe(candidates)

    def _build_prompt(self, question):
        return (
            "Database schema:\n"
            "{schema}\n\n"
            "Question: {question}\n\n"
            "Write exactly one SQLite query that answers the question.\n"
            "Reply with a single