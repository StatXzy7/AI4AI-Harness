"""Majority-vote harness: asks solver for 3 SQL attempts at temperature 0.7, executes all parsing SQL, and returns the most common successful result."""
import re
from collections import Counter
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        # Step 1: ask the solver for 3 independent SQL attempts
        raw_responses = self.llm(
            prompt=question,
            system="",
            temperature=0.7,
            n=3,
        )

        # Ensure raw_responses is iterable; if single string, wrap
        if isinstance(raw_responses, str):
            raw_responses = [raw_responses]

        # Step 2: extract SQL from each response and execute the parseable ones
        candidate_sqls = []
        execution_results = []  # parallel list of result rows (or error marker) per SQL
        successful_sqls = []

        for raw in raw_responses:
            if not isinstance(raw, str):
                continue
            sql = bridge.extract_sql(raw)
            if not sql:
                continue
            candidate_sqls.append(sql)
            exec_result = self.execute(sql)
            if exec_result.get("ok"):
                successful_sqls.append(sql)
                execution_results.append(exec_result.get("rows", []))

        # Step 3: majority vote on execution results among successful SQLs
        if successful_sqls:
            # Use frozenset of tuple(row) for hashable comparison
            result_keys = []
            for rows in execution_results:
                key = frozenset(tuple(r.items()) if isinstance(r, dict) else tuple(r)
                                for r in rows)
                result_keys.append(key)

            result_counter = Counter(result_keys)
            top_key, top_count = result_counter.most_common(1)[0]
            # majority means strictly more than half; if tie, take the first one
            if top_count > len(result_keys) / 2:
                winning_idx = result_keys.index(top_key)
                return successful_sqls[winning_idx]
            else:
                # tie or no majority — return the first successful SQL
                return successful_sqls[0]

        # Step 4: fallback — if nothing executed successfully, return the first extracted SQL
        # (even if invalid; harness contract demands a string)
        if candidate_sqls:
            return candidate_sqls[0]

        # Last resort: empty SQL
        return ""