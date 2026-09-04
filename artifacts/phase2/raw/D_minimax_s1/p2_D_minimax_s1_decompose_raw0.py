"""Plan-to-Pieces-to-SQL harness: decomposes a question into ordered sub-questions, answers each with a focused LLM call, then assembles the final SQL."""
from __future__ import annotations

import json
import re
from typing import List

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS1Decompose(SQLHarness):
    """
    Plan-to-Pieces-to-SQL (decomposition) harness.

    Control flow:
      1. Use the LLM to PLAN: emit an ordered list of sub-questions that, together,
         answer the user's question against the provided schema.
      2. For each sub-question, in order, call the LLM to produce a small piece of
         analysis (intermediate reasoning) grounded in the schema.
      3. Assemble the sub-answers + plan + original question into a final prompt
         that asks for a single SQL statement.
      4. Extract the SQL, sanity-check it (run against execute), and return.
    """

    # ----------------- helpers -----------------

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """Find the first JSON-looking block (list or object) in a string."""
        if not text:
            return ""
        # Try fenced