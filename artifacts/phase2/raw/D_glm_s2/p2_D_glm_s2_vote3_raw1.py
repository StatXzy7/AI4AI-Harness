"""Self-consistency wrapper over the frozen solver: draw 3 independent SQL candidates at temperature 0.7, execute every one that parses, and return the candidate whose result set wins the majority vote."""

from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2DGlmS2Vote3"]


class P2P2DGlmS2Vote3(SQLHarness):
    """3-sample result-level self-consistency voting around a frozen weak solver.

    The strategy is realized in the control flow, not just the prompt:

    1. A single call to ``self.llm`` with ``n=3`` and ``temperature=0.7``
       yields three *independent* SQL attempts for the question.
    2. Each attempt is parsed with ``bridge.extract_sql``; every attempt that
       parses to a non-empty SQL string is executed against the database.
    3. Each successful execution casts one vote for its result set (rows),
       so repeated SQL across samples is naturally weighted by multiplicity.
    4. The SQL belonging to the majority result set is returned; ties are
       broken deterministically by first occurrence among the samples.
    5. Fallbacks: if nothing parses, return ``""``; if nothing executes
       successfully, return the first parseable candidate (best effort).
    """

    N_SAMPLES = 3
    SAMPLE_TEMPERATURE = 0.7

    SYSTEM_PROMPT = (
        "You are a precise text-to-SQL translator. Given a database schema and "
        "a question, output exactly one SQLite query and nothing else: no "
        "explanation, no markdown fences, no commentary."
    )

    USER_TEMPLATE = (
        "Database schema:\n"
        "{schema}\n"
        "\n"
        "Question: {question}\n"
        "\n"
        "Write a single SQL query that answers the question."
    )

    def solve(self, question: str) -> str:
        prompt = self.USER_TEMPLATE.format(schema=self.schema, question=question)

        # --- 1) three independent attempts from the frozen solver ---------
        raw = self.llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=self.SAMPLE_TEMPERATURE,
            n=self.N_SAMPLES,
        )
        samples = [raw] if isinstance(raw, str) else list(raw)

        # --- 2) keep every attempt that parses ----------------------------
        candidates = []
        for text in samples:
            try:
                sql = bridge.extract_sql(text)
            except Exception:
                sql = None
            if sql:
                sql = sql.strip()
            if sql:
                candidates.append(sql)

        if not candidates:
            return ""

        # --- 3) execute all of them, vote on result sets ------------------
        votes = Counter()          # result key -> number of successful runs
        first_seen = {}            # result key -> order of first appearance
        representative = {}        # result key -> one SQL producing it
        for sql in candidates:
            result = self._safe_execute(sql)
            if not result or not result.get("ok"):
                continue  # failed execution: no result, therefore no vote
            key = self._result_key(result)
            if key not in first_seen:
                first_seen[key] = len(first_seen)
                representative[key] = sql
            votes[key] += 1

        # --- 4) majority result; ties broken by earliest first seen -------
        if votes:
            best_key = min(votes, key=lambda k: (-votes[k], first_seen[k]))
            return representative[best_key]

        # --- 5) nothing executed: best-effort first parseable candidate ---
        return candidates[0]

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _safe_execute(self, sql):
        """Run ``self.execute`` defensively; never let it raise."""
        try:
            return self.execute(sql)
        except Exception:
            return None

    @staticmethod
    def _result_key(result):
        """Hashable, order-sensitive key for a successful execution result."""
        rows = result.get("rows")
        if rows is None:
            rows = ()
        try:
            key = tuple(
                tuple(row) if isinstance(row, (list, tuple)) else (row,)
                for row in rows
            )
            hash(key)
            return key
        except TypeError:
            # Unhashable cell values (dicts, etc.): fall back to repr.
            return ("__unhashable__", repr(rows))