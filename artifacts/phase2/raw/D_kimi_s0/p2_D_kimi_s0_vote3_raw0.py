"""Self-consistency voting harness: sample 3 independent SQL candidates at temperature 0.7, execute every candidate that parses, and return the SQL whose execution result forms the majority."""

from ..harness_base import SQLHarness
from .. import bridge


class P2P2DKimiS0Vote3(SQLHarness):
    """3-sample self-consistency Text-to-SQL solver with execution-based majority voting."""

    def solve(self, question: str) -> str:
        prompt = (
            "Write a single SQL query that answers the question using the "
            "database schema below.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Respond with only the SQL query."
        )
        system = "You are an expert Text-to-SQL engine that outputs only valid SQL."

        # Step 1: draw 3 independent samples from the frozen solver.
        response = self.llm(prompt, system=system, temperature=0.7, n=3)
        raw_texts = self._as_texts(response)

        # Step 2: extract SQL from each sample; keep only candidates that parse.
        candidates = []
        for text in raw_texts:
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                candidates.append(sql.strip())

        if not candidates:
            # Nothing parseable at all: best-effort fallback.
            return bridge.extract_sql(raw_texts[0]) if raw_texts else ""

        # Step 3: execute every parseable candidate (identical SQL strings
        # are executed only once but still count separately in the vote).
        cache = {}
        buckets = {}  # normalized result -> [sql, ...], in candidate order
        for sql in candidates:
            if sql not in cache:
                cache[sql] = self.execute(sql)
            outcome = cache[sql]
            if not outcome.get("ok"):
                continue
            key = self._normalize_rows(outcome.get("rows"))
            buckets.setdefault(key, []).append(sql)

        if not buckets:
            # No candidate executed successfully: fall back to the first
            # parseable SQL rather than returning nothing.
            return candidates[0]

        # Step 4: majority vote over result sets. max() returns the first
        # maximal element and buckets preserve candidate insertion order,
        # so ties break deterministically toward the earliest candidate.
        winning_sqls = max(buckets.values(), key=len)
        return winning_sqls[0]

    @staticmethod
    def _as_texts(response) -> list:
        """Normalize the llm(n=3) response into a list of raw text strings."""
        if isinstance(response, str):
            return [response]
        try:
            items = list(response)
        except TypeError:
            return [str(response)]
        texts = []
        for item in items:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                texts.append(str(item.get("text") or item.get("content") or ""))
            else:
                texts.append(str(getattr(item, "text", item)))
        return texts

    @staticmethod
    def _normalize_rows(rows):
        """Hashable, row-order-insensitive fingerprint of an execution result."""
        if rows is None:
            return ("__no_rows__",)
        normalized = []
        for row in rows:
            if isinstance(row, dict):
                normalized.append(tuple(sorted((str(k), repr(v)) for k, v in row.items())))
            elif isinstance(row, (list, tuple)):
                normalized.append(tuple(repr(v) for v in row))
            else:
                normalized.append(repr(row))
        return tuple(sorted(normalized))