"""Self-consistency wrapper around the frozen solver: draw 3 independent SQL attempts (n=3, temperature=0.7), execute every one that parses, and return the SQL behind the majority result."""

from typing import Any, Dict, List, Optional, Tuple

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS1Vote3"]


class P2P2CGlmS1Vote3(SQLHarness):
    """Draws 3 independent SQL attempts from the frozen solver (n=3, temperature=0.7), executes every one that parses, and returns the SQL whose result set wins the majority vote."""

    N_SAMPLES = 3       # independent attempts requested from the solver
    TEMPERATURE = 0.7   # sampling temperature for those attempts

    SYSTEM_PROMPT = (
        "You are a precise text-to-SQL translator. "
        "Reply with exactly one SQLite query and nothing else."
    )

    PROMPT_TEMPLATE = (
        "Database schema:\n"
        "{schema}\n"
        "\n"
        "Question: {question}\n"
        "\n"
        "Write one SQL query that answers the question above. "
        "Put the query in a