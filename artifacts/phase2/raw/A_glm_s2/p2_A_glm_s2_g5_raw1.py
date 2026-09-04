"""Execution-agreement voting: draw K candidate SQL queries (a greedy anchor plus diverse samples), execute every distinct candidate, and return the representative of the cluster of candidates whose database results won the most votes."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G5(SQLHarness):
    """Self-consistency voting over sampled SQL, with votes pooled by execution result."""

    K_SAMPLES = 5             # total generations: 1 greedy anchor + 4 diverse samples
    SAMPLE_TEMPERATURE = 0.8  # temperature for the diverse (non-anchor) samples
    MAX_EXECUTIONS = 8        # hard cap on how many distinct queries get executed

    def solve(self, question: str) -> str:
        system = (
            "You are an expert text-to-SQL translator. Given a database schema and a "
            "natural-language question, write exactly one SQLite SELECT query that "
            "answers it. Use only tables and columns that appear in the schema. "
            "Reply with the query alone inside a