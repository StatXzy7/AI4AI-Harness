"""Sample 3 independent SQL attempts at temperature 0.7, execute each parseable one, and return the query whose result set wins the majority vote."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS2Vote3(SQLHarness):
    """Self-consistency harness: draw n=3 samples at T=0.7, execute all parsed SQL, majority-vote on execution results."""

    NUM_SAMPLES = 3
    TEMPERATURE = 0.7

    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL solver. Given a database schema and "
            "a natural-language question, write a single SQL query that answers "
            "it. Respond with the SQL only, optionally inside a