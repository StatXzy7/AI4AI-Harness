"""Two-stage refinement: first stage drafts SQL, second stage criticizes and repairs based on schema context."""
# MECHANISM: twostage

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G7(SQLHarness):
    def solve(self, question: str) -> str:
        # Stage 1: produce a draft SQL using the frozen weak solver.
        draft_prompt = (
            "Given the database schema below, write a single SQLite SQL query that answers the question.\n\n"
            "SCHEMA:\n" + self.schema + "\n\n"
            "QUESTION:\n" + question + "\n\n"
            "Return ONLY the SQL query, no explanation."
        )
        draft_text = self.llm(draft_prompt, system="", temperature=0.0, n=1)
        draft_sql = bridge.extract_sql(draft_text)
        if not draft_sql:
            return draft_text.strip()

        # Stage 2: a critic/repair pass that consumes the draft and the schema.
        # It is allowed to rewrite the SQL using schema knowledge the drafter may have missed.
        review_prompt = (
            "You are reviewing a draft SQL query for correctness against the schema.\n"
            "Fix any mistakes: wrong table/column names, missing joins, wrong aggregation, "
            "ambiguous references, or syntax issues. Use SQLite dialect.\n\n"
            "SCHEMA:\n" + self.schema + "\n\n"
            "QUESTION:\n" + question + "\n\n"
            "DRAFT SQL:\n" + draft_sql + "\n\n"
            "Return ONLY the corrected SQL query."
        )
        review_text = self.llm(review_prompt, system="", temperature=0.0, n=1)
        final_sql = bridge.extract_sql(review_text)
        if not final_sql:
            # Fall back to the draft if the critic produced nothing extractable.
            return draft_sql
        return final_sql