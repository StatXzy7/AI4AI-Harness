"""Two independently generated SQL formulations (a flat join-based query and a nested subquery-based query) are both executed, and the first one whose result set is non-empty is returned."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS2TwoView(SQLHarness):
    """Two-view weak solver: a JOIN-style candidate and a SUBQUERY-style candidate
    are generated in independent LLM calls, both are executed, and selection
    prefers the first non-empty result (ties go to the first view)."""

    NAME = "p2p2d_glm_s2_two_view"

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL translator for SQLite. Given a database "
        "schema and a natural-language question, write exactly one SQL query that "
        "answers it. Output only the SQL inside a single