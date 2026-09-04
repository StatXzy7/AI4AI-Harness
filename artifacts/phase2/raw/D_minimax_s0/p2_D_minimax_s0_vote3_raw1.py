"""Voting harness that generates 3 SQL attempts and returns the majority-voted executable result."""
from typing import Any, List, Tuple
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS0Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        """Ask the solver for 3 SQL attempts, execute all that parse, return the majority result."""
        # Step 1: Generate 3 independent SQL attempts with higher temperature for diversity
        raw_outputs: List[str] = self.llm(
            question,
            system="",
            temperature=0.7,
            n=3,
        )

        # Step 2: Parse each output and collect (sql, exec_result) pairs
        candidate_results: List[Tuple[str, dict]] = []

        for raw in raw_outputs:
            sql = bridge.extract_sql(raw)
            if not sql:
                continue
            result = self.execute(sql)
            # Only keep successfully executed SQL
            if result.get("ok"):
                candidate_results.append((sql, result))

        # Step 3: If we have at least one successful execution, vote on rows
        if candidate_results:
            rows_counter: Counter = Counter()
            for _, result in candidate_results:
                # Use a hashable representation of rows for voting
                rows_key = tuple(tuple(row) for row in result.get("rows", []))
                rows_counter[rows_key] += 1

            # Majority-winner rows (most common execution result)
            majority_rows = rows_counter.most_common(1)[0][0]

            # Find the SQL that produced the majority rows; on tie pick the first
            for sql, result in candidate_results:
                rows_key = tuple(tuple(row) for row in result.get("rows", []))
                if rows_key == majority_rows:
                    return sql

            # Fallback: return the first candidate's SQL
            return candidate_results[0][0]

        # Step 4: No successful execution -- return the best-effort parsed SQL from the first output
        for raw in raw_outputs:
            sql = bridge.extract_sql(raw)
            if sql:
                return sql

        return ""