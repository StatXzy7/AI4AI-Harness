"""Parses the question's 'Hint:' line, restates it as numbered hard requirements that steer SQL generation, and guard-repairs the query until deterministic literal checks, live execution, and an LLM audit all pass."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2HintGuard(SQLHarness):
    """Hint-guarded Text-to-SQL harness.

    The strategy is implemented in the control flow, not merely in the prompt:

      1. ``_parse_hint`` splits the raw question into (hint, body).
      2. ``_restate_requirements`` rewrites the hint as a numbered list of
         HARD REQUIREMENTS, captured as structured data.
      3. ``_generate_sql`` writes SQL under those binding requirements.
      4. The guard loop in ``solve`` then runs deterministic literal /
         identifier checks, executes the SQL against the database, and
         LLM-audits it against every requirement, repairing until all
         guards pass or the repair budget is exhausted (in which case the
         last runnable query is returned).
    """

    MAX_REPAIR_ROUNDS = 3

    _HINT_RE = re.compile(r"(?is)\bhint\s*:\s*(.*)$")

    # ------------------------------------------------------------------
    # LLM / SQL plumbing
    # ------------------------------------------------------------------
    def _chat(self, prompt, system="", temperature=0.0):
        """Call the frozen solver and normalise its reply to a string."""
        out = self.llm(prompt, system=system, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return (out or "").strip()

    @staticmethod
    def _to_sql(raw_text, fallback=""):
        """Extract SQL from an LLM reply, falling back to cleaned raw text."""
        sql = bridge.extract_sql(raw_text)
        if not sql:
            txt = raw_text.strip()
            txt = re.sub(r"(?is)^\s*