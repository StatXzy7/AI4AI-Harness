"""Self-consistency voting: draw one greedy plus several temperature-diverse SQL samples from the frozen solver, execute each distinct candidate, and return the query whose execution result wins the weighted vote."""
# MECHANISM: vote

import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G7(SQLHarness):
    """Execution-level self-consistency (vote) around the frozen weak solver.

    Control flow -- a real change versus a single greedy generation call:

      1. SAMPLE   -- K completions are drawn from the frozen solver: the first
                     at temperature 0.0 (greedy anchor) and K-1 more at a
                     higher temperature for diversity.
      2. MERGE    -- every completion is reduced to one normalised, read-only
                     SELECT/WITH statement; identical statements merge and pool
                     their sample weight.
      3. EXECUTE  -- each distinct candidate is executed once on the database.
      4. VOTE     -- candidates are clustered by an order-insensitive signature
                     of their result rows; the cluster with the highest total
                     weight wins (ties go to the cluster holding the earliest,
                     i.e. the greedy, sample).
      5. FALLBACK -- if no candidate executes cleanly, a text-level vote over
                     the failing candidates decides; if nothing usable was
                     extracted at all, a trivial query is returned.

    Note: execution results are only ever used to *compare* candidates; they
    are never fed back into the LLM, so this is purely a vote mechanism.
    """

    K = 5
    DIVERSE_TEMPERATURE = 0.7
    SIGNATURE_ROW_CAP = 50

    SYSTEM = (
        "You are a senior data analyst who writes precise SQLite queries. "
        "Always answer with exactly one read-only SQL query and nothing else."
    )

    _DESTRUCTIVE = re.compile(
        r"(?i)\b("
        r"insert|update|delete|drop|alter|create|replace|truncate|"
        r"attach|detach|reindex|vacuum"
        r")\b"
    )

    # ---------------------------------------------------------------- solve

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)

        # 1. SAMPLE: greedy anchor + diverse draws -------------------------
        samples = [self._one(self.llm(prompt, system=self.SYSTEM))]
        for _ in range(self.K - 1):
            samples.append(
                self._one(
                    self.llm(
                        prompt,
                        system=self.SYSTEM,
                        temperature=self.DIVERSE_TEMPERATURE,
                    )
                )
            )

        # 2. MERGE: extract, normalise, safety-filter, deduplicate ---------
        candidates = []      # [first_sample_index, sql, weight]
        index_of = {}        # sql -> position in candidates
        raw_any = ""         # first normalised extraction, for last resort
        for idx, raw in enumerate(samples):
            text = self._extract(raw)
            norm = self._normalize_sql(text)
            if norm and not raw_any:
                raw_any = norm
            sql = self._candidate(text)
            if not sql:
                continue
            if sql in index_of:
                candidates[index_of[sql]][2] += 1
            else:
                index_of[sql] = len(candidates)
                candidates.append([idx, sql, 1])

        # 3. EXECUTE every distinct candidate, 4. VOTE on results ----------
        clusters = {}        # signature -> [weight, first_sample_index, sql]
        failures = []        # candidates that did not execute cleanly
        for first_idx, sql, weight in candidates:
            outcome = self._safe_execute(sql)
            if outcome is not None and outcome.get("ok"):
                signature = self._signature(outcome.get("rows"))
                if signature is None:          # uncomparable -> own bucket
                    signature = ("__uncomparable__", first_idx)
                bucket = clusters.get(signature)
                if bucket is None:
                    clusters[signature] = [weight, first_idx, sql]
                else:
                    bucket[0] += weight
                    bucket[1] = min(bucket[1], first_idx)
            else:
                failures.append([first_idx, sql, weight])

        if clusters:
            _weight, _first, winner = max(
                clusters.values(), key=lambda b: (b[0], -b[1])
            )
            return winner

        # 5. FALLBACKS ------------------------------------------------------
        if failures:                            # text-level vote among failures
            failures.sort(key=lambda f: (-f[2], f[0]))
            return failures[0][1]
        if raw_any and self._harmless(raw_any):  # model's own output, if safe
            return raw_any
        return "SELECT 1;"

    # -------------------------------------------------------------- helpers

    def _build_prompt(self, question: str) -> str:
        schema = (self.schema or "").strip()
        return (
            "Database schema (SQLite dialect):\n"
            "----------------\n"
            f"{schema}\n"
            "----------------\n\n"
            f"Question: {(question or '').strip()}\n\n"
            "Write exactly one SQLite query that answers the question.\n"
            "Rules:\n"
            "- Read-only: one single SELECT (or WITH ... SELECT) statement.\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Reply with the query alone inside one