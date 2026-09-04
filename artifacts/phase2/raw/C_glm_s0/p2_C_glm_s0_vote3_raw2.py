"""Draws three independent SQL samples from the frozen solver at temperature 0.7, executes every sample that parses, and returns the query whose execution result wins the majority vote."""

import json

from ..harness_base import SQLHarness
from .. import bridge


class P2P2CGlmS0Vote3(SQLHarness):
    """Execution-level self-consistency: 3 temperature-0.7 samples -> parse -> execute all -> majority vote on results."""

    VOTES = 3
    TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL assistant. Given a database schema and a natural "
        "language question, respond with exactly one SQL query and nothing else."
    )

    INSTRUCTION = (
        "Write a single SQL query that answers the question using only the schema above. "
        "Output only the SQL query."
    )

    def solve(self, question: str) -> str:
        schema = self.schema if isinstance(self.schema, str) else ""

        # Built by concatenation so braces in the schema/question cannot break formatting.
        prompt = (
            "Database schema:\n" + schema
            + "\n\nQuestion: " + question
            + "\n\n" + self.INSTRUCTION
        )

        # ---- Step 1: three INDEPENDENT attempts from the frozen solver ----
        # High temperature + n=3 gives diverse candidates to vote over.
        raw = self.llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=self.TEMPERATURE,
            n=self.VOTES,
        )
        if raw is None:
            return ""
        completions = list(raw) if isinstance(raw, (list, tuple)) else [raw]
        completions = [c for c in completions if isinstance(c, str)][: self.VOTES]

        # ---- Step 2: parse every attempt; keep the ones that yield SQL ----
        candidates = []
        for text in completions:
            sql = (bridge.extract_sql(text) or "").strip()
            if sql.endswith(";"):
                sql = sql[:-1].strip()
            if sql:
                candidates.append(sql)

        if not candidates:
            # Nothing parsed: last-resort fallback to the first non-empty raw sample.
            for text in completions:
                if text and text.strip():
                    return text.strip()
            return ""

        # ---- Step 3: EXECUTE every parsed candidate ----
        # Memoized per unique SQL text (saves work), but each attempt keeps its own vote.
        cache = {}
        executed = []  # (sql, outcome, signature) — one entry per attempt occurrence
        for sql in candidates:
            if sql not in cache:
                cache[sql] = self.execute(sql) or {}
            outcome = cache[sql]
            executed.append((sql, outcome, self._result_signature(outcome)))

        # ---- Step 4: majority vote over successful execution results ----
        # Only error-free executions count as votable "results"; ties break toward
        # the earliest-sampled candidate for determinism.
        counts = {}
        first_seen = []
        for _sql, outcome, sig in executed:
            if not outcome.get("ok"):
                continue
            if sig not in counts:
                counts[sig] = 0
                first_seen.append(sig)
            counts[sig] += 1

        if first_seen:
            winner = max(first_seen, key=lambda s: counts[s])  # ties -> earliest
            for sql, outcome, sig in executed:
                if outcome.get("ok") and sig == winner:
                    return sql

        # ---- Fallback: no candidate executed successfully ----
        # Return the first parsed attempt rather than an arbitrary one.
        return candidates[0]

    @staticmethod
    def _result_signature(outcome):
        """Canonical string form of an execution result, used as the vote key.

        Two queries that return the same rows (even if written differently)
        share a signature and therefore vote together.
        """
        rows = outcome.get("rows")
        try:
            return json.dumps(rows, sort_keys=True, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            return repr(rows)