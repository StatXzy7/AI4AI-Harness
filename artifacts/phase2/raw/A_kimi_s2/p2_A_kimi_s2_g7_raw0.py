"""Iterative repair harness: generate SQL greedily, execute it, and feed execution errors back to the frozen solver for regeneration until the query runs or the attempt budget is exhausted."""
# MECHANISM: repair

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS2G7(SQLHarness):
    """Generate -> execute -> repair loop wrapping the frozen weak solver.

    The improvement over a single greedy call is a closed feedback loop:
    every candidate query is actually executed, and any database error is
    handed back to the solver together with the failing query so it can
    produce a corrected rewrite. A repeated-identical-query detector breaks
    repair stalls by escalating temperature once before giving up.
    """

    MAX_ATTEMPTS = 4

    SYSTEM_PROMPT = (
        "You are an expert SQL query writer. Given a database schema and a "
        "natural-language question, you write a single syntactically valid SQL "
        "query that answers the question. You output only the SQL query."
    )

    def solve(self, question: str) -> str:
        schema = self.schema

        initial_prompt = (
            "Database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. "
            "Output only the SQL, no explanation."
        )

        # Step 1: initial greedy generation.
        sql = bridge.extract_sql(
            self.llm(initial_prompt, system=self.SYSTEM_PROMPT, temperature=0.0, n=1)
        )

        if not sql:
            # Extraction failed entirely: re-ask with an explicit format demand.
            sql = bridge.extract_sql(
                self.llm(
                    initial_prompt
                    + "\n\nRespond with ONLY the SQL query inside a