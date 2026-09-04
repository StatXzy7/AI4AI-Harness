"""Majority-vote harness that asks the frozen solver for 3 SQL attempts and returns the winning query."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS1Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: Ask the frozen solver for 3 independent SQL attempts at temperature=0.7.
        raw_responses = self.llm(question, system="", temperature=0.7, n=3)

        # Step 2: Parse each candidate response into a SQL string.
        candidates = []
        for resp in raw_responses:
            sql = bridge.extract_sql(resp)
            if sql:
                candidates.append(sql)

        if not candidates:
            # Nothing parsed -- fall back to the first raw response's extracted SQL (already empty),
            # so we return an empty string rather than raising.
            return ""

        # Step 3: Execute every candidate that successfully parsed. Group their row-sets.
        # Majority is determined by the canonicalized result rows (stringified).
        result_to_sql = {}   # canonical_rows -> first sql that produced them
        canonical_to_count = {}  # canonical_rows -> tally

        for sql in candidates:
            res = self.execute(sql)
            if not res.get("ok"):
                continue
            rows = res.get("rows", [])
            # Make rows hashable / comparable by stringifying deterministically.
            try:
                key = repr([tuple(r) for r in rows])
            except TypeError:
                key = repr(rows)

            if key not in result_to_sql:
                result_to_sql[key] = sql
            canonical_to_count[key] = canonical_to_count.get(key, 0) + 1

        if not canonical_to_count:
            # Nothing executed successfully; return the first parsed candidate.
            return candidates[0]

        # Step 4: Pick the result with the highest vote count (majority).
        winning_key = max(canonical_to_count.items(), key=lambda kv: kv[1])[0]
        return result_to_sql[winning_key]