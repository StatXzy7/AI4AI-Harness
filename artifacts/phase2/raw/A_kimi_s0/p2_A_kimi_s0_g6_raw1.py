"""Improve the frozen solver by sampling several SQL candidates and electing the one whose execution result wins a majority vote."""
# MECHANISM: vote        -- you draw multiple samples and select among them

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G6(SQLHarness):
    """Self-consistency style voting harness.

    Rather than trusting a single greedy decoding, this harness draws
    NUM_SAMPLES candidates: one greedy call (temperature 0.0) plus several
    at increasing temperatures for diversity. Each distinct candidate query
    is executed once (results are cached so duplicates still cast votes
    without re-executing). Candidates that run successfully are clustered
    by their normalized result sets, and a representative of the largest
    cluster is returned. Ties are broken in favor of the greedy candidate,
    so the harness never regresses below the single-call baseline. If no
    candidate executes successfully, the greedy candidate is returned.
    """

    NUM_SAMPLES = 5
    TEMPERATURE_SCHEDULE = (0.0, 0.3, 0.6, 0.8, 1.0)
    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL translator. Given a database schema "
        "and a natural-language question, produce exactly one syntactically "
        "valid SQL query that answers the question. Output only the SQL "
        "query inside a single