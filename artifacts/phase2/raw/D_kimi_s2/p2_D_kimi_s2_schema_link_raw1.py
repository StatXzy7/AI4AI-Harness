"""Two-stage Text-to-SQL harness: schema-link the question to its mentioned tables/columns, then generate and repair SQL against that linked subset."""

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2SchemaLink(SQLHarness):
    """Stage 1 (schema linking): select the tables/columns relevant to the
    question via an LLM pass UNION a deterministic mention-matching pass.
    Stage 2 (generation): produce SQL constrained to the linked subset, with
    execution-feedback repair."""

    MAX_REPAIRS = 2

    # ----------------------------- utilities -----------------------------

    def _ask(self, prompt, system=""):
        out = self.llm(prompt, system=system, temperature=0.0, n=1)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    @staticmethod
    def _norm(text):
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(text).lower())).strip()

    @staticmethod
    def _clean_sql(raw):
        sql = bridge.extract_sql(raw)
        if sql and sql.strip():
            return sql.strip()
        text = raw.strip()
        m = re.search(r"