"""Self-consistency voting: sample multiple SQL candidates, execute them, and return the query whose result set wins the majority vote."""
# MECHANISM: vote        -- you draw multiple samples and select among them

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS1G5(SQLHarness):
    """Execution-filtered self-consistency ("vote") Text-to-SQL harness.

    Control flow:
      1. One greedy generation anchors the candidate pool.
      2. Several high-temperature samples add diverse alternatives.
      3. Each distinct candidate SQL is executed against the database;
         candidates that raise execution errors are discarded.
      4. Survivors vote with their (order-insensitive) result sets; the
         query from the largest agreeing group is returned. Ties, and the
         "everything failed to execute" case, fall back to the greedy
         candidate.
    """

    _SYSTEM = (
        "You are an expert SQLite data analyst. Given a database schema and a "
        "natural-language question, you write a single correct SQLite SELECT "
        "query that answers the question. You output only SQL, never prose."
    )
    _NUM_SAMPLES = 4
    _SAMPLE_TEMPERATURE = 0.7

    # ------------------------------------------------------------------ API
    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)

        # 1) Greedy anchor + 2) diverse sampled alternatives.
        raw_outputs = self._call_llm(prompt, temperature=0.0)
        for _ in range(self._NUM_SAMPLES):
            try:
                raw_outputs.extend(
                    self._call_llm(prompt, temperature=self._SAMPLE_TEMPERATURE)
                )
            except Exception:
                break

        # Extract and deduplicate candidate SQL (greedy candidate is first).
        candidates, seen = [], set()
        for text in raw_outputs:
            try:
                sql = (bridge.extract_sql(text) or "").strip()
            except Exception:
                continue
            if not sql:
                continue
            key = " ".join(sql.split()).rstrip(";")
            if key and key not in seen:
                seen.add(key)
                candidates.append(sql)

        if not candidates:
            if not raw_outputs:
                return ""
            fallback = bridge.extract_sql(raw_outputs[0])
            return fallback or raw_outputs[0]

        # 3) Execute every distinct candidate; only successful ones may vote.
        buckets = []  # each entry: [result_fingerprint, vote_count, sql]
        for sql in candidates:
            try:
                outcome = self.execute(sql)
            except Exception:
                continue
            if not isinstance(outcome, dict) or not outcome.get("ok"):
                continue
            fingerprint = self._canon_rows(outcome.get("rows"))
            for bucket in buckets:
                if bucket[0] == fingerprint:
                    bucket[1] += 1
                    break
            else:
                buckets.append([fingerprint, 1, sql])

        if not buckets:
            return candidates[0]

        # 4) Majority vote; ties keep the earliest-executed (greedy-anchored)
        #    bucket because dict/list order is insertion order.
        return max(buckets, key=lambda b: b[1])[2]

    # -------------------------------------------------------------- helpers
    def _build_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQLite SELECT query that answers the question.\nSQL:"
        )

    def _call_llm(self, prompt: str, temperature: float):
        out = self.llm(prompt, system=self._SYSTEM, temperature=temperature, n=1)
        if isinstance(out, (list, tuple)):
            return [str(x) for x in out]
        return [str(out)]

    @staticmethod
    def _canon_rows(rows):
        """Order-insensitive, type-robust fingerprint of a result set."""
        if rows is None:
            return None
        canon = []
        for row in rows:
            if isinstance(row, dict):
                canon.append(tuple(sorted((str(k), repr(v)) for k, v in row.items())))
            elif isinstance(row, (list, tuple)):
                canon.append(tuple(repr(v) for v in row))
            else:
                canon.append((repr(row),))
        try:
            return tuple(sorted(canon))
        except TypeError:
            return tuple(canon)