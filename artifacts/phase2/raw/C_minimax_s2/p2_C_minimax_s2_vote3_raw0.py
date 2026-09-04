"""Harness that asks the weak solver for 3 independent SQL attempts and returns the majority-voted result."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            f"Given the following database schema:\n\n{self.schema}\n\n"
            f"Generate a single SQL query that answers this question:\n{question}\n\n"
            "Return only the SQL query with no additional explanation or formatting."
        )

        # Ask the solver for 3 independent SQL attempts.
        candidates = self.llm(prompt, system="", temperature=0.7, n=3)
        if isinstance(candidates, str):
            candidates = [candidates]

        # Execute all candidates that successfully parse via the bridge.
        results = []
        for text in candidates:
            sql = bridge.extract_sql(text)
            if not sql:
                continue
            outcome = self.execute(sql)
            if outcome.get("ok"):
                results.append(sql)

        if not results:
            return ""

        # Majority vote over successfully executed SQL candidates.
        vote_counts: dict[str, int] = {}
        for sql in results:
            vote_counts[sql] = vote_counts.get(sql, 0) + 1

        max_count = max(vote_counts.values())
        winners = [sql for sql, count in vote_counts.items() if count == max_count]

        # Pick the first winner in original order to preserve stability.
        for sql in results:
            if sql in winners:
                return sql

        return winners[0]