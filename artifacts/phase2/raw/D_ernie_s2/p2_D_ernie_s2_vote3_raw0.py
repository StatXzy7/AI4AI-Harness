"""Generate three independent SQL candidates via a frozen weak solver, execute each, and return the majority valid result."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DErnieS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        """
        Ask the weak solver for three independent SQL attempts (temperature=0.7, n=3),
        execute every attempt that parses successfully, and return the SQL that appears
        most frequently among the successful executions (majority vote).
        """
        # Build the prompt that includes the schema and the natural‑language question.
        prompt = f"{self.schema}\n\nQuestion: {question}\nSQL:"

        # Obtain three independent completions from the frozen weak solver.
        raw_attempts = self.llm(prompt, system="", temperature=0.7, n=3)

        # Extract SQL strings from each raw attempt.
        sql_candidates = [bridge.extract_sql(text) for text in raw_attempts]

        # Execute each candidate and keep those that parse (i.e., execution succeeds).
        successful_sqls = []
        for sql in sql_candidates:
            try:
                result = self.execute(sql)
                if result.get("ok", False):
                    successful_sqls.append(sql)
            except Exception:
                # If extraction or execution raises, treat as failure.
                continue

        if not successful_sqls:
            # No valid SQL could be produced; return empty string.
            return ""

        # Count occurrences of each successful SQL and pick the majority.
        vote_counts = {}
        for sql in successful_sqls:
            vote_counts[sql] = vote_counts.get(sql, 0) + 1

        # Determine the SQL with the highest vote count.
        majority_sql = max(vote_counts, key=vote_counts.get)

        return majority_sql