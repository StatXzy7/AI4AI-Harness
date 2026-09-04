"""Generate three independent SQL candidates with temperature 0.7, execute the valid ones, and return the majority SQL string."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CErnieS1Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        # Build the prompt using the provided schema and the user question.
        prompt = f"Schema:\n{self.schema}\n\nQuestion: {question}\nSQL:"

        # Ask the LLM for three independent attempts.
        raw_outputs = self.llm(prompt, system="", temperature=0.7, n=3)

        # Extract SQL strings from each raw output.
        candidates = [bridge.extract_sql(text) for text in raw_outputs]

        # Execute each candidate and keep those that parse successfully.
        parsed = []
        for sql in candidates:
            result = self.execute(sql)
            if result.get("ok", False):
                parsed.append(sql)

        # If no candidate parsed, fall back to the first extracted SQL.
        if not parsed:
            return candidates[0] if candidates else ""

        # Determine the majority SQL string.
        # Count occurrences; in case of a tie, pick the first among the tied ones.
        counts = {}
        for sql in parsed:
            counts[sql] = counts.get(sql, 0) + 1

        # Find the maximum count.
        max_count = max(counts.values())
        # Collect all SQL strings with that count.
        majority_options = [sql for sql, cnt in counts.items() if cnt == max_count]

        # Return the first majority option (resolves ties deterministically).
        return majority_options[0]