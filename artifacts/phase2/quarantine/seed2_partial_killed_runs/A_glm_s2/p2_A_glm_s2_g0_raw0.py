"""Draw several temperature-sampled SQL candidates for the question, execute every one of them, and return the candidate whose result set wins a majority vote across the samples (execution-result self-consistency)."""

# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS2G0(SQLHarness):
    """Self-consistency voting over executed result sets.

    Control flow per question:
      1. One greedy candidate (temperature 0.0) plus N_SAMPLES stochastic
         candidates (temperature SAMPLE_TEMPERATURE) are generated from the
         same schema-conditioned prompt.
      2. Every candidate is executed against the database (results are cached
         per distinct SQL text so duplicates are only run once).
      3. Candidates that fail to execute are discarded; the survivors vote by
         their *result signature* (an order-insensitive canonical form of the
         returned rows), so queries that disagree syntactically but agree
         semantically still pool their votes.
      4. The signature with the most votes wins; ties are broken in favour of
         non-empty result sets, then in favour of the candidate that appeared
         earliest (which privileges the greedy sample).  If no candidate
         executes at all, the greedy candidate is returned as a fallback.
    """

    N_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.8

    SYSTEM = (
        "You are an expert text-to-SQL engineer. Respond with a single, valid "
        "SQLite SELECT statement and nothing else."
    )

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #
    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)

        # ---- stage 1: draw the candidate pool -------------------------- #
        candidates = []
        greedy = self._generate(prompt, 0.0)
        if greedy:
            candidates.append(greedy)
        for _ in range(self.N_SAMPLES):
            sql = self._generate(prompt, self.SAMPLE_TEMPERATURE)
            if sql:
                candidates.append(sql)

        if not candidates:
            # last-ditch: one more greedy attempt with a minimal prompt
            retry = self._generate(
                "Schema:\n%s\n\nQuestion: %s\n\nSQL:" % (self._schema_text(), question),
                0.0,
            )
            return retry or ""

        # ---- stage 2: execute every candidate (dedup via cache) -------- #
        cache = {}       # sql text -> (ok, signature)
        executions = []  # parallel to candidates
        for sql in candidates:
            if sql not in cache:
                cache[sql] = self._execute(sql)
            executions.append(cache[sql])

        # ---- stage 3: vote over execution signatures -------------------- #
        tally = {}  # signature -> list of sample indices voting for it
        for idx, (ok, sig) in enumerate(executions):
            if ok:
                tally.setdefault(sig, []).append(idx)

        if not tally:
            # nothing ran: fall back to the greedy candidate
            return candidates[0]

        best_sig = None
        best_key = None
        for sig, idxs in tally.items():
            # votes first, then prefer non-empty results, then earlier sample
            key = (len(idxs), 1 if sig else 0, -min(idxs))
            if best_key is None or key > best_key:
                best_sig, best_key = sig, key

        winner_idx = tally[best_sig][0]
        return candidates[winner_idx]

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _schema_text(self) -> str:
        schema = getattr(self, "schema", "")
        if schema is None:
            return ""
        if isinstance(schema, (list, tuple)):
            return "\n".join(str(s) for s in schema)
        return str(schema)

    def _build_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            "----------------\n"
            "{schema}\n"
            "----------------\n\n"
            "Task: write ONE SQLite query that answers the question below, using "
            "only the tables and columns shown in the schema.\n"
            "Guidelines:\n"
            "- Return exactly one SELECT statement.\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Join tables on their keys when the question spans several tables.\n"
            "- Prefer explicit column names over SELECT *.\n"
            "- Wrap the final query in a