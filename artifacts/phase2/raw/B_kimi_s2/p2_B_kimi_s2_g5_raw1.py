"""Self-consistency harness: sample multiple SQL candidates, execute each, and return the candidate whose result set wins a multiplicity-weighted majority vote."""
# MECHANISM: vote -- you draw multiple samples and select among them

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G5(SQLHarness):
    NUM_SAMPLES = 6
    SAMPLE_TEMPERATURE = 0.8

    SYSTEM = (
        "You are an expert SQLite text-to-SQL assistant. Given a database "
        "schema and a natural-language question, write exactly one SQL query "
        "that answers the question. Output only the query inside a