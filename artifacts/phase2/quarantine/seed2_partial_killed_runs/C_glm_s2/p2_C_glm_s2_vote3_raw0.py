"""Self-consistency harness: sample 3 independent SQL candidates from the frozen solver at temperature 0.7, execute every candidate that parses, and return the query whose execution result wins the majority vote."""

import hashlib
from collections import defaultdict

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS2Vote3(SQLHarness):
    """
    Voting wrapper around a frozen weak Text-to-SQL solver.

    Control flow per question:
      1. Draw SAMPLES (=3) independent completions in one call
         (n=3, temperature=0.7).
      2. Extract SQL from each sample and execute *every* one that parses
         (no early exit, no dedup -- each sample carries one vote).
      3. Group successful executions by their result set and return the SQL
         of the majority group (ties broken by earliest attempt).
    """

    SAMPLES = 3          # independent solver attempts per question
    TEMPERATURE = 0.7    # sampling temperature for those attempts

    _SYSTEM = (
        "You are an expert text-to-SQL translator. "
        "Reply with a single valid SQLite SELECT query and nothing else."
    )

    # ------------------------------------------------------------------
    # Main control flow
    # ------------------------------------------------------------------
    def solve(self, question: str) -> str:
        question = question or ""

        # --- Phase 1: 3 independent attempts from the frozen solver. ---
        attempts = self._sample(question, self.TEMPERATURE, self.SAMPLES)

        # --- Phase 2: execute *every* attempt that parses. ---
        votes = []
        for idx, text in enumerate(attempts):
            sql = self._extract(text)
            if not sql:
                continue  # unparseable sample -> no vote
            ok, rows = self._execute(sql)
            votes.append({
                "sql": sql,
                "idx": idx,                      # sample order (tie-breaker)
                "ok": ok,
                "sig": self._signature(rows) if ok else None,
            })

        # --- Phase 3: majority vote over results. ---
        if votes:
            successful = [v for v in votes if v["ok"]]
            if successful:
                # Majority over *execution results*: two attempts count as
                # the same vote iff their queries return the same rows.
                # Failed executions are deliberately excluded -- an erroring
                # query must never outvote a query that produced rows.
                pool, key_of = successful, (lambda v: v["sig"])
            else:
                # Degenerate case: every execution errored. Fall back to a
                # majority vote over the (normalised) SQL text itself.
                pool, key_of = votes, (lambda v: self._normalize(v["sql"]))

            groups = defaultdict(list)
            for v in pool:
                groups[key_of(v)].append(v)

            # Largest group wins; ties broken by earliest attempt index.
            winning = min(
                groups.values(),
                key=lambda g: (-len(g), min(v["idx"] for v in g)),
            )

            # Deterministic representative of the winning group:
            # shortest SQL, then lexicographically smallest.
            return min((v["sql"] for v in winning), key=lambda s: (len(s), s))

        # --- Safety net: none of the samples parsed -> one greedy attempt. ---
        for text in self._sample(question, 0.0, 1):
            sql = self._extract(text)
            if sql:
                return sql

        return ""

    # ------------------------------------------------------------------
    # Solver interaction
    # ------------------------------------------------------------------
    def _sample(self, question, temperature, n):
        """One call to the frozen solver; output normalised to a list of texts."""
        try:
            raw = self.llm(
                self._prompt(question),
                system=self._SYSTEM,
                temperature=temperature,
                n=n,
            )
        except Exception:
            return []
        return self._as_texts(raw)

    def _prompt(self, question):
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            "Write exactly one SQL query (SQLite dialect) that answers the "
            "question below.\n"
            "Output only the query in a