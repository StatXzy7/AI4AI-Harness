"""Sample three independent SQL candidates from the frozen solver (n=3, temperature=0.7), execute every attempt that parses, and return the SQL whose result set wins the majority vote."""

import json
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS2Vote3(SQLHarness):
    """Self-consistency voting harness over three sampled solver attempts."""

    NAME = "P2P2DGlmS2Vote3"
    ATTEMPTS = 3
    TEMPERATURE = 0.7

    SYSTEM = (
        "You are an expert data analyst. Using only the provided database "
        "schema, write exactly one SQLite query that answers the question."
    )

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #
    def _prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "----------------\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Instructions:\n"
            "- Output a single SQLite SELECT statement.\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Return only the SQL (a