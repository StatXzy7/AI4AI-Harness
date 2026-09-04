"""Text-to-SQL harness that generates SQL greedily, executes it, and iteratively repairs it by feeding execution errors (or empty results) back to the LLM for regeneration."""
# MECHANISM: repair      -- you execute SQL and feed execution errors back for regeneration
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G1(SQLHarness):
    """Generate -> execute -> repair loop.

    Instead of trusting the first greedy generation, we run the candidate SQL
    against the database. If execution fails (or returns zero rows), the error
    message / empty-result observation is appended to a repair prompt and the
    model is asked to produce a corrected query. This repeats for a bounded
    number of rounds; the most recent candidate is returned as a fallback.
    """

    MAX_ATTEMPTS = 4  # 1 initial generation + up to 3 repair rounds

    SYSTEM = (
        "You are an expert SQLite query writer. Given a database schema and a "
        "natural-language question, you output a single correct SQL query. "
        "You output only SQL, never explanations or prose."
    )

    def _generate(self, question: str) -> str:
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite query that answers the question. "
            "Output only the SQL, with no commentary."
        )
        text = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
        return bridge.extract_sql(text)

    def _repair(self, question: str, bad_sql: str, feedback: str) -> str:
        prompt = (
            f"Database schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            f"Your previous SQL query was:\n