"""Voting harness that samples multiple SQL candidates and picks the most consistent executable one."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BMinimaxS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        candidates = []
        n_samples = 5
        for _ in range(n_samples):
            prompt = (
                f"You are an expert SQL generator. Given the schema and question, "
                f"produce a single SQLite SQL statement.\n\n"
                f"Schema:\n{self.schema}\n\n"
                f"Question:\n{question}\n\n"
                f"Return ONLY the SQL."
            )
            raw = self.llm(prompt, system="", temperature=0.7, n=1)
            sql = bridge.extract_sql(raw)
            if sql:
                candidates.append(sql)

        if not candidates:
            prompt = (
                f"Schema:\n{self.schema}\n\nQuestion:\n{question}\n\n"
                f"Write a single SQLite SQL query. Return only SQL."
            )
            raw = self.llm(prompt, system="", temperature=0.0, n=1)
            return bridge.extract_sql(raw) or ""

        # First, try deterministic greedy for tie-breaking
        greedy_prompt = (
            f"Schema:\n{self.schema}\n\nQuestion:\n{question}\n\n"
            f"Write a single SQLite SQL query. Return only SQL."
        )
        greedy_raw = self.llm(greedy_prompt, system="", temperature=0.0, n=1)
        greedy_sql = bridge.extract_sql(greedy_raw)
        if greedy_sql:
            candidates.append(greedy_sql)

        # Execute each candidate and group by result equivalence
        buckets = {}
        for sql in candidates:
            res = self.execute(sql)
            if not res.get("ok", False):
                key = ("ERROR", res.get("error", ""))
            else:
                rows = res.get("rows", [])
                key = ("ROWS", repr(rows))
            buckets.setdefault(key, []).append(sql)

        # Pick the bucket with most votes; prefer one that executed successfully
        best_key = None
        best_count = -1
        for key, sqls in buckets.items():
            if key[0] == "ERROR":
                continue
            if len(sqls) > best_count:
                best_count = len(sqls)
                best_key = key

        if best_key is None:
            # All candidates errored; fall back to greedy if present, else first candidate
            return greedy_sql if greedy_sql else candidates[0]

        chosen = buckets[best_key][0]
        return chosen