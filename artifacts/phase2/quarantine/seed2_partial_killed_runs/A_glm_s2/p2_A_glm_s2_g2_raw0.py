"""Greedy SQL generation hardened by an execution-repair loop: every candidate query is executed, and when the database reports an error, that error message is fed back to the model for up to three corrective regenerations before falling back to the last candidate."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G2(SQLHarness):
    """One greedy draft plus up to three error-conditioned regeneration rounds."""

    MAX_REPAIR_ROUNDS = 3
    MAX_ERROR_CHARS = 500

    SYSTEM_PROMPT = (
        "You are an expert SQLite programmer. Using only the tables and columns "
        "defined in the provided schema, write exactly one SQLite query that "
        "answers the question. Output only the query inside a single