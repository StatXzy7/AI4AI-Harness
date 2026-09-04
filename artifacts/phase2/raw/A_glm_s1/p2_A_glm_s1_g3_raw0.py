"""Draw several sampled SQL candidates, execute each against the database, and return the query whose execution result wins a cross-sample consensus vote."""

# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G3(SQLHarness):
    """Execution-aware self-consistency voting over sampled SQL candidates.

    Control flow per question:
      1. Draw TOTAL_SAMPLES candidate queries from the frozen solver:
         one greedy anchor (temperature 0) plus diverse samples (temperature
         SAMPLE_TEMPERATURE), each parsed with bridge.extract_sql.
      2. De-duplicate the candidates while keeping their multiplicity.
      3. Execute every distinct candidate on the real database.
      4. Group candidates by an execution-result signature (the rows they
         return) and pick a query from the strongest agreeing group.
      5. If nothing executes, fall back to a plain plurality vote on the
         query text, preferring SELECT-shaped queries.
    """

    NAME = "P2P2AGlmS1G3"

    TOTAL_SAMPLES = 6           # LLM generations per question (1 greedy + 5 sampled)
    SAMPLE_TEMPERATURE = 0.8    # temperature for the diverse (non-anchor) samples
    RESULT_CAP = 64             # max rows hashed into an execution signature
    SAFE_HEADS = {"SELECT", "WITH", "VALUES"}

    # ------------------------------------------------------------------ #
    # prompting
    # ------------------------------------------------------------------ #
    def _system(self) -> str:
        return (
            "You are an expert SQLite data analyst. Given a database schema "
            "and a natural-language question, you write exactly one correct, "
            "executable SQLite SELECT query."
        )

    def _prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "------------\n"
            f"{self.schema}\n"
            "------------\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite query that answers the question.\n"
            "Rules:\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Qualify columns with their table name when joins are involved.\n"
            "- Do not invent columns, tables, or literal values.\n"
            "- Return only the query inside a single