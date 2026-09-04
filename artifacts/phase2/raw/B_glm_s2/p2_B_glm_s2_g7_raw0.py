"""Self-consistency voting over executed results: several SQL samples are drawn, each is executed against the database, and the candidate whose result set earns the most sample votes is returned."""
# MECHANISM: vote

import json

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G7(SQLHarness):
    """Improves on a single greedy call by voting across samples and using the
    database itself as the judge: every distinct candidate is executed,
    candidates are grouped into equivalence classes by the result they actually
    produce, and the class with the most sample votes wins."""

    NAME = "P2P2BGlmS2G7"

    N_SAMPLES = 5                # total candidates: 1 greedy anchor + 4 diverse
    DIVERSE_TEMPERATURE = 0.8    # sampling temperature for the non-greedy draws
    MAX_SIGNATURE_ROWS = 50      # rows considered when fingerprinting a result

    SYSTEM = (
        "You are an expert SQLite analyst. Reply with exactly one SQL query "
        "inside a single