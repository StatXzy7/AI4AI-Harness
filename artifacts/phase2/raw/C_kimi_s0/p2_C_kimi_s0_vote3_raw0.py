"""Sample 3 independent SQL candidates (n=3, temperature=0.7), execute every candidate that parses, and return the query whose result set wins the majority vote."""

import json
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CKimiS0Vote3(SQLHarness):
    """Self-consistency harness: draw 3 samples, execute them, majority-vote on results."""

    N_SAMPLES = 3
    TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are an expert Text-to-SQL assistant. Given a database schema and "
        "a natural-language question, write a single correct SQL query. "
        "Output only the SQL query, with no explanation."
    )

    def solve(self, question: str) -> str:
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. Return only the SQL."
        )

        # --- Step 1: ask the solver for 3 independent attempts ---------------
        completions = self.llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=self.TEMPERATURE,
            n=self.N_SAMPLES,
        )
        if isinstance(completions, str):
            completions = [completions]
        completions = [self._as_text(c) for c in (completions or [])]

        # --- Step 2: extract SQL; keep only candidates that parse ------------
        candidates = []
        for text in completions:
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                candidates.append(sql.strip())

        if not candidates:
            return "SELECT 1"  # no parseable attempt at all

        # --- Step 3: execute every parseable candidate -----------------------
        # Cache by SQL text so duplicate samples keep their vote weight
        # without paying for a duplicate execution.
        results = []  # list of (sql, canonical_result)
        cache = {}
        for sql in candidates:
            if sql in cache:
                canon = cache[sql]
            else:
                try:
                    outcome = self.execute(sql)
                except Exception:
                    outcome = None
                if outcome and outcome.get("ok"):
                    canon = self._canon_rows(outcome.get("rows", []))
                else:
                    canon = None
                cache[sql] = canon
            if canon is not None:
                results.append((sql, canon))

        if not results:
            # Nothing executed successfully: fall back to the first parseable SQL.
            return candidates[0]

        # --- Step 4: majority vote over canonicalized result sets ------------
        counts = Counter(canon for _, canon in results)
        winning_canon, _ = counts.most_common(1)[0]  # ties resolve to first-seen
        for sql, canon in results:
            if canon == winning_canon:
                return sql
        return results[0][0]

    @staticmethod
    def _as_text(completion) -> str:
        if isinstance(completion, str):
            return completion
        if isinstance(completion, dict):
            for key in ("text", "content", "message"):
                if key in completion:
                    return str(completion[key])
        return str(completion)

    @staticmethod
    def _canon_rows(rows) -> str:
        try:
            return json.dumps(rows, sort_keys=True, default=str)
        except (TypeError, ValueError):
            return repr(rows)