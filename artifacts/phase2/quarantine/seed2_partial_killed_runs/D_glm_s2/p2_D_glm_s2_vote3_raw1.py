"""Self-consistency harness: draws 3 independent SQL candidates from the frozen solver at temperature 0.7, executes every parseable attempt, and returns the query whose result set wins the majority vote."""

import json
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DGlmS2Vote3(SQLHarness):
    """3-sample self-consistency voting over execution results."""

    N_SAMPLES = 3
    TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL translator. "
        "Respond with exactly one SQL query and nothing else."
    )

    def _build_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "%s\n\n"
            "Using only the schema above, write a single SQL query that answers "
            "the question below. Output only the SQL query itself -- no prose, "
            "no markdown fences, no explanation.\n\n"
            "Question: %s" % (self.schema, question)
        )

    @staticmethod
    def _normalize_samples(response):
        # self.llm(..., n=3) should return a list of completions; be tolerant
        # of a single string or non-string payloads.
        if isinstance(response, (list, tuple)):
            return [t if isinstance(t, str) else str(t) for t in response]
        return [str(response)]

    @staticmethod
    def _result_key(rows):
        # Canonical, hashable fingerprint of a result set for voting.
        try:
            return json.dumps(rows, sort_keys=True, default=str)
        except (TypeError, ValueError):
            return repr(rows)

    def solve(self, question: str) -> str:
        # 1) Draw 3 independent attempts from the frozen solver (high temp).
        raw = self.llm(
            self._build_prompt(question),
            system=self.SYSTEM_PROMPT,
            temperature=self.TEMPERATURE,
            n=self.N_SAMPLES,
        )
        samples = self._normalize_samples(raw)[: self.N_SAMPLES]

        # 2) Parse every attempt; keep order and duplicates (each = one vote).
        candidates = []
        for text in samples:
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                candidates.append(sql.strip())

        # Nothing parseable at all: emit a harmless, valid query.
        if not candidates:
            return "SELECT 1"

        # 3) Execute every parseable attempt; record successful results.
        executed = []  # (sql, result_key) in attempt order
        for sql in candidates:
            try:
                outcome = self.execute(sql)
            except Exception:
                continue
            if isinstance(outcome, dict) and outcome.get("ok"):
                executed.append((sql, self._result_key(outcome.get("rows"))))

        # 4) Majority vote over execution results: the most common result set
        #    wins; ties break toward the earliest attempt producing it.
        if executed:
            counts = Counter(key for _, key in executed)
            top = max(counts.values())
            for sql, key in executed:
                if counts[key] == top:
                    return sql

        # 5) Fallback: nothing executed cleanly -> majority vote on SQL text.
        text_counts = Counter(candidates)
        top = max(text_counts.values())
        for sql in candidates:
            if text_counts[sql] == top:
                return sql