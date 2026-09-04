"""Repair-loop Text-to-SQL harness: greedily draft a query, execute it against the real database, and feed the exact engine error (or a zero-row advisory) back to the frozen solver for up to three corrective regenerations, returning the first query that executes successfully."""
# MECHANISM: repair

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G6(SQLHarness):
    """Greedy draft + execution-verified repair loop.

    The improvement over a single greedy call is pure control flow:

      1. one greedy generation produces a candidate SQL string;
      2. the candidate is *executed* against the database;
      3. on failure (engine error, non-read-only output, no SQL extracted)
         the exact failure message is quoted back into a repair prompt and
         the solver regenerates a corrected query;
      4. steps 2-3 repeat up to ``MAX_REPAIRS`` times;
      5. a query that executes but returns zero rows gets exactly one
         advisory round: the model may answer ``KEEP`` (empty answer is
         correct) or propose a rewrite, which is adopted only if it is
         itself a clean read-only SELECT and is then re-verified.
    """

    MAX_REPAIRS = 3  # extra solver calls budgeted for repairs

    _SYSTEM = (
        "You are an expert SQL engineer. You answer with a single read-only "
        "SELECT query and output nothing except SQL."
    )

    # string literals / quoted identifiers, scrubbed before the safety scan
    _SCRUB_RE = re.compile(r"'(?:[^']|'')*'|\"[^\"]*\"|`[^`]*`|\[[^\]]*\]")
    _WRITE_RE = re.compile(
        r"\b(insert|update|delete|drop|alter|create|replace|truncate|"
        r"attach|detach|pragma|vacuum|reindex)\b",
        re.IGNORECASE,
    )

    # ------------------------------------------------------------------- llm
    def _call(self, prompt: str) -> str:
        """One greedy call to the frozen solver; raw text out."""
        try:
            out = self.llm(prompt, system=self._SYSTEM, temperature=0.0)
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if out is None: