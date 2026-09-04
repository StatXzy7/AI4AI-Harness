"""Two-view text-to-SQL harness: independently draft a join-based and a subquery-based SQL for the question, execute both, and return the SQL whose execution yields rows — taking the first formulation when both are non-empty and the first cleanly-executing one otherwise."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS2TwoView(SQLHarness):
    """Solve by dual formulation (join view vs. subquery view) with execution-based selection."""

    NAME = "P2P2DGlmS2TwoView"

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "natural-language question, output exactly one SQLite query inside a "
        "