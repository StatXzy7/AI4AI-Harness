"""P2P2D harness that samples 3 SQL attempts from Minimax at temperature 0.7 and returns the majority successful execution result."""
from collections import Counter
from ..harness_base import SQLHarness
from .. import bridge


class P2P2DMinimaxS2Vote3(SQLHarness):
    def solve(self, question: str) -> str:
        system_prompt = (
            "You are a text-to-SQL generator. Produce exactly one SQL statement that answers "
            "the question against the provided schema. Return ONLY the SQL, no explanation."
        )
        user_prompt = f"Schema:\n{self.schema}\n\nQuestion: {question}\n\nSQL:"

        # Ask the frozen solver for 3 independent attempts at temperature 0.7
        responses = self.llm(user_prompt, system=system_prompt, temperature=0.7, n=3)

        sqls = []
        for r in responses:
            sql = bridge.extract_sql(r)
            if sql:
                sqls.append(sql)

        # Drop duplicates that collapse to the same string -- they don't add evidence
        # but we still keep order for tie-breaking consistency.
        if not sqls:
            # Fallback: return the first raw response stripped so the caller gets *something*.
            return responses[0].strip() if responses else ""

        # Execute every parseable SQL and keep only those that succeeded.
        executed = []  # list of (sql, signature) where signature is the row fingerprint
        for sql in sqls:
            result = self.execute(sql)
            if result.get("ok"):
                # Build a deterministic signature of the result rows so the vote is on outcomes.
                rows = result.get("rows") or []
                try:
                    signature = repr(sorted(tuple(r) for r in rows))
                except TypeError:
                    signature = repr(rows)
                executed.append((sql, signature))

        if not executed:
            # Nothing executed cleanly -- return the first extracted SQL so the caller
            # still sees the best attempt.
            return sqls[0]

        # Majority vote on execution signatures.
        sig_counter = Counter(sig for _, sig in executed)
        top_sig, top_count = sig_counter.most_common(1)[0]

        # Tie-break: if the top signature count is tied with another, prefer the one
        # that appears earliest among the sampled attempts.
        tied_signatures = [s for s, c in sig_counter.items() if c == top_count]
        if len(tied_signatures) > 1:
            for _, sig in executed:
                if sig in tied_signatures:
                    top_sig = sig
                    break

        # Return the first sampled SQL that produced the winning signature.
        for sql, sig in executed:
            if sig == top_sig:
                return sql

        return executed[0][0]