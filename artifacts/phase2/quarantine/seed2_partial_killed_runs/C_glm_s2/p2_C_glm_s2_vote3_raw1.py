"""Wrap the frozen solver with execution-based self-consistency: draw 3 independent SQL attempts at temperature 0.7, execute every one that parses, and return the attempt whose result set wins the majority vote."""

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2CGlmS2Vote3"]


class P2P2CGlmS2Vote3(SQLHarness):
    """Self-consistency harness: sample 3 SQL candidates, execute all that
    parse, and majority-vote on the executed result sets."""

    # --- configuration --------------------------------------------------
    N_SAMPLES = 3
    TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are an expert SQL analyst. Given a database schema and a "
        "question, answer with exactly one SQL query."
    )

    # --- helpers ----------------------------------------------------------

    @staticmethod
    def _as_texts(samples):
        """Normalize whatever self.llm() returned into a list of strings."""
        if samples is None:
            return []
        if isinstance(samples, str):
            return [samples]
        texts = []
        for item in samples:
            if item is None:
                continue
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                texts.append(item.get("text") or item.get("content") or "")
            else:
                texts.append(str(item))
        return texts

    def _build_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "----------------\n"
            f"{self.schema}\n"
            "----------------\n\n"
            f"Question: {question}\n\n"
            "Write a single SQL query that answers the question. "
            "Respond with the SQL query only."
        )

    def _sample_attempts(self, question: str):
        """One call to the frozen solver asking for N_SAMPLES independent
        completions; extract a candidate SQL string from each completion."""
        raw = self.llm(
            self._build_prompt(question),
            system=self.SYSTEM_PROMPT,
            temperature=self.TEMPERATURE,
            n=self.N_SAMPLES,
        )
        attempts = []
        for text in self._as_texts(raw)[: self.N_SAMPLES]:
            sql = (bridge.extract_sql(text) or "").strip()
            if sql:
                attempts.append(sql)
        return attempts

    # --- main entry point -------------------------------------------------

    def solve(self, question: str) -> str:
        # 1) Ask the frozen solver for 3 independent SQL attempts
        #    (single call, n=3, temperature=0.7).
        attempts = self._sample_attempts(question)
        if not attempts:
            # Nothing parseable came back; report failure with empty SQL.
            return ""

        # 2) Execute every attempt that parsed. Failed executions simply
        #    cast no vote rather than aborting the vote.
        votes = Counter()        # result-key -> number of attempts producing it
        winner_sql = {}          # result-key -> first SQL that produced it
        any_ok = False

        for sql in attempts:
            try:
                outcome = self.execute(sql)
            except Exception as exc:  # defensive: executor itself crashed
                outcome = {"ok": False, "rows": [], "error": str(exc)}
            if not isinstance(outcome, dict):
                outcome = {}

            if not outcome.get("ok"):
                continue

            any_ok = True
            key = repr(outcome.get("rows"))  # canonical view of the result set
            votes[key] += 1
            winner_sql.setdefault(key, sql)

        # 3) Majority vote over the executed result sets
        #    (ties broken by first-encountered result).
        if any_ok:
            best_key = None
            best_count = -1
            for key, count in votes.items():
                if count > best_count:
                    best_key, best_count = key, count
            return winner_sql[best_key]

        # 4) Nothing executed successfully: fall back to the first parseable
        #    candidate so the pipeline still gets a SQL string.
        return attempts[0]