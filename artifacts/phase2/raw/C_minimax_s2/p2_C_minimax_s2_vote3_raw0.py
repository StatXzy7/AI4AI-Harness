"""Majority-vote harness that generates 3 SQL candidates at temperature 0.7 and returns the SQL for the most common successful execution result."""
import re
from collections import Counter
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        prompt = (
            "You are a Text-to-SQL expert. Given the schema below and the user's "
            "question, produce a single correct SQL statement.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL, no prose."
        )

        # Step 1: ask the weak solver for 3 independent attempts
        raw = self.llm(prompt, system="", temperature=0.7, n=3)

        # Normalize the response into a list of candidate texts
        if isinstance(raw, list):
            candidates = raw
        elif isinstance(raw, str):
            # Some backends return one string even with n>1; split on common delimiters
            candidates = re.split(r"\n\s*\n|(?i)^\s*SQL\s*\d+\s*[:\-]\s*$|^---\s*$",
                                 raw, flags=re.MULTILINE)
            candidates = [c for c in candidates if c.strip()]
            if not candidates:
                candidates = [raw]
        else:
            candidates = [str(raw)]

        # Step 2: extract and execute each candidate; collect (result_signature, sql) pairs
        executed = []
        for text in candidates:
            sql = bridge.extract_sql(text)
            if not sql:
                continue
            res = self.execute(sql)
            if res.get("ok"):
                # Build a signature: prefer rows; fall back to error/exec info
                rows = res.get("rows")
                sig = ("rows", tuple(tuple(r) for r in rows)) if rows else ("empty",)
                executed.append((sig, sql, rows))

        if not executed:
            # No candidate parsed/executed successfully: return the first extracted SQL anyway
            for text in candidates:
                sql = bridge.extract_sql(text)
                if sql:
                    return sql
            return ""

        # Step 3: majority vote over successful execution signatures
        sig_counter = Counter(sig for sig, _, _ in executed)
        top_sig, _ = sig_counter.most_common(1)[0]

        # Among candidates sharing the top signature, prefer the shortest SQL
        winners = [sql for sig, sql, _ in executed if sig == top_sig]
        if len(winners) == 1:
            return winners[0]
        return min(winners, key=lambda s: (len(s), s))