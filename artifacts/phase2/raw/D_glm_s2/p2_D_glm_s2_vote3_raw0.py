"""Majority-vote self-consistency harness: draws three independent SQL attempts from the frozen solver in one sampled call (n=3, temperature=0.7), parses and executes every attempt, and returns the query whose result set wins the vote."""

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2Vote3"]


class P2P2DGlmS2Vote3(SQLHarness):
    """3-vote self-consistency wrapper: sample -> parse -> execute -> majority."""

    NAME = "P2P2DGlmS2Vote3"

    # Strategy knobs.
    VOTES = 3            # independent attempts per question
    TEMPERATURE = 0.7    # sampling temperature that makes them independent
    MAX_TOPUPS = 3       # bounded re-asks if the backend under-delivers attempts

    SYSTEM = (
        "You are an expert text-to-SQL engineer. "
        "Answer with exactly one SQLite SQL query and nothing else."
    )

    PROMPT = """Database schema:
{schema}

Question: {question}

Write a single SQLite SQL query that answers the question.
Return only the query, enclosed in a