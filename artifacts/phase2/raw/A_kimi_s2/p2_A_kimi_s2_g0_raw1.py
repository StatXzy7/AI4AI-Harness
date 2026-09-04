"""Sample several candidate SQL queries and select the winner by execution-based majority voting."""
# MECHANISM: vote        -- you draw multiple samples and select among them

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G0(SQLHarness):
    """Wrap the frozen solver with sampled self-consistency: draw N candidate
    queries at nonzero temperature, execute each unique candidate once, and
    return the query whose result set attracts the most sample weight."""

    NUM_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.7
    FALLBACK_SQL = "SELECT 1"

    SYSTEM_PROMPT = (
        "You are an expert SQLite developer. Given a database schema and a "
        "natural-language question, write exactly one correct SQL query. "
        "Output only the SQL query, wrapped in a