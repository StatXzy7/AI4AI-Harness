"""Execution-grounded self-consistency: draw several sampled SQL candidates, execute each against the database, and return the candidate whose result set wins the majority vote."""
# MECHANISM: vote        -- you draw multiple samples and select among them

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS0G4(SQLHarness):
    """Self-consistency voting harness.

    Instead of a single greedy decode, this harness samples NUM_SAMPLES
    diverse candidate queries at a non-zero temperature, executes each
    distinct candidate, and groups them by the signature of their result
    sets. The candidate from the largest result-set cluster is returned,
    so agreement among independently sampled queries (grounded in actual
    execution) decides the answer rather than the model's single most
    likely continuation.
    """

    NUM_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.8

    def solve(self, question: str) -> str:
        system = (
            "You are an expert text-to-SQL engine. Given a database schema and a "
            "natural-language question, write exactly one SQL query that answers it. "
            "Output only the SQL query, with no explanation or formatting."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. Output only the SQL."
        )

        # --- Stage 1: draw multiple diverse samples in one call. ---
        samples = self.llm(
            prompt,
            system=system,
            temperature=self.SAMPLE_TEMPERATURE,
            n=self.NUM_SAMPLES,
        )
        if isinstance(samples, str):
            samples = [samples]

        candidates = []
        for sample in samples:
            sql = bridge.extract_sql(sample)
            if sql and sql.strip():
                candidates.append(sql.strip())

        # Degenerate case: nothing parseable. Fall back to one greedy decode.
        if not candidates:
            fallback = self.llm(prompt, system=system, temperature=0.0, n=1)
            if isinstance(fallback, (list, tuple)):
                fallback = fallback[0]
            return bridge.extract_sql(fallback)

        # --- Stage 2: execute each distinct candidate once and tally votes. ---
        sig_cache = {}   # sql -> result-set signature, or None if execution failed
        votes = {}       # signature -> number of samples producing it
        choice = {}      # signature -> first candidate sql that produced it
        order = []       # insertion order of signatures, for deterministic tie-breaks

        for sql in candidates:
            if sql not in sig_cache:
                outcome = self.execute(sql)
                if outcome.get("ok"):
                    sig_cache[sql] = self._rows_signature(outcome.get("rows"))
                else:
                    sig_cache[sql] = None
            signature = sig_cache[sql]
            if signature is None:
                continue  # errored candidates abstain from the vote
            if signature not in votes:
                votes[signature] = 0
                choice[signature] = sql
                order.append(signature)
            votes[signature] += 1

        # If every candidate failed to execute, return the first sample as-is.
        if not votes:
            return candidates[0]

        # --- Stage 3: majority vote; earliest cluster wins ties. ---
        winner = max(order, key=lambda sig: votes[sig])
        return choice[winner]

    @staticmethod
    def _rows_signature(rows) -> str:
        """Order-insensitive, type-tolerant fingerprint of a result set."""
        try:
            return repr(sorted(repr(row) for row in rows))
        except Exception:
            return repr(rows)