"""Sample several SQL candidates from the frozen solver and elect, by weighted majority vote over execution-result equivalence classes, the query to return."""

# MECHANISM: vote        -- you draw multiple samples and select among them

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2BGlmS1G6"]


class P2P2BGlmS1G6(SQLHarness):
    """Execution-guided self-consistency voting over sampled SQL candidates.

    Control flow (a real change vs. a single greedy call):

      1. Draw TOTAL_SAMPLES candidates from the frozen solver: one greedy
         call (temperature 0.0) plus TOTAL_SAMPLES-1 sampled calls at
         SAMPLE_TEMPERATURE, each with a slightly different framing so the
         samples do not collapse onto a single answer.
      2. Extract and normalize the SQL of every sample; identical strings are
         pooled so each sample contributes exactly one vote.
      3. Execute every distinct candidate (read-only statements only) and
         bucket candidates by their result rows, so semantically equal
         queries share a bucket even when their text differs.
      4. Return the SQL of the heaviest bucket (most sample votes); ties are
         broken toward the bucket containing the greedy sample, then toward
         the earlier sample. If nothing can be verified by execution, fall
         back to the most frequently sampled raw candidate.
    """

    TOTAL_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.8
    MAX_SIGNATURE_ROWS = 50

    _SYSTEM_BASE = (
        "You are an expert SQLite analyst. Given a database schema and a "
        "question, output exactly one SQL query and nothing else."
    )

    # Decorrelating framings for the non-greedy samples.
    _HINTS = [
        "First decide which tables are needed and how they join on foreign keys.",
        "First decide whether aggregation, GROUP BY, or HAVING is needed.",
        "First decide whether DISTINCT, ORDER BY, or LIMIT changes the answer.",
        "First pin down the exact WHERE conditions, including quoting and date formats.",
    ]

    # Statements we are willing to run in order to compare results.
    _EXECUTABLE_HEADS = ("SELECT", "WITH", "VALUES", "TABLE")

    def solve(self, question: str) -> str:
        candidates = self._collect_candidates(question)
        if not candidates:
            return ""
        if len(set(candidates)) == 1:
            # Unanimous samples: there is nothing to vote between.
            return candidates[0]
        return self._elect(candidates)

    # ------------------------------------------------------------------
    # Stage 1: draw the candidate pool (1 greedy + N-1 sampled variants).
    # ------------------------------------------------------------------
    def _collect_candidates(self, question):
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite query that answers the question. "
            "Output only the SQL query."
        )
        candidates = []
        for i in range(self.TOTAL_SAMPLES):
            greedy = i == 0
            system = self._SYSTEM_BASE
            if not greedy:
                system = system + " " + self._HINTS[(i - 1) % len(self._HINTS)]
            temperature = 0.0 if greedy else self.SAMPLE_TEMPERATURE
            try:
                text = self.llm(prompt, system=system, temperature=temperature, n=1)
            except Exception:
                continue
            try:
                sql = self._normalize_sql(bridge.extract_sql(self._as_text(text)))
            except Exception:
                continue
            if sql:
                candidates.append(sql)
        return candidates

    # ------------------------------------------------------------------
    # Stage 2: elect a winner via execution-result equivalence classes.
    # ------------------------------------------------------------------
    def _elect(self, candidates):
        counts, first_index, ordered = {}, {}, []
        for idx, sql in enumerate(candidates):
            if sql not in counts:
                counts[sql] = 0
                first_index[sql] = idx
                ordered.append(sql)
            counts[sql] += 1

        greedy_sql = candidates[0]

        # signature -> [weight, first_idx, best_sql, has_greedy]
        clusters = {}
        unverified = []
        for sql in ordered:
            signature = self._try_execute(sql)
            if signature is None:
                unverified.append(sql)
                continue
            cluster = clusters.get(signature)
            if cluster is None:
                clusters[signature] = cluster = [0, first_index[sql], sql, False]
            cluster[0] += counts[sql]
            if sql == greedy_sql:
                cluster[3] = True

        best_sql, best_score = None, None
        for cluster in clusters.values():
            score = (cluster[0], 1 if cluster[3] else 0, -cluster[1])
            if best_score is None or score > best_score:
                best_sql, best_score = cluster[2], score
        if best_sql is not None:
            return best_sql

        # Nothing could be verified by execution: fall back to the most
        # frequently sampled candidate (earliest sample breaks ties).
        if unverified:
            return max(unverified, key=lambda s: (counts[s], -first_index[s]))
        return candidates[0]

    # ------------------------------------------------------------------
    # Helpers.
    # ------------------------------------------------------------------
    def _try_execute(self, sql):
        """Execute a read-only candidate; return a result signature or None."""
        head = sql.split(None, 1)[0].upper() if sql else ""
        if head not in self._EXECUTABLE_HEADS:
            return None  # never run anything that could mutate the database
        try:
            result = self.execute(sql)
        except Exception:
            return None
        if not isinstance(result, dict) or not result.get("ok"):
            return None
        return self._signature(result.get("rows"))

    @classmethod
    def _signature(cls, rows):
        """Canonical key for a result table (row count + leading rows)."""
        try:
            rows = list(rows) if rows is not None else []
        except Exception:
            rows = []
        normalized = []
        for row in rows[: cls.MAX_SIGNATURE_ROWS]:
            if isinstance(row, dict):
                normalized.append(
                    ("dict",) + tuple(sorted((repr(k), repr(v)) for k, v in row.items()))
                )
            elif isinstance(row, (list, tuple)):
                normalized.append(("seq",) + tuple(repr(v) for v in row))
            else:
                normalized.append(("scalar", repr(row)))
        return (len(rows), tuple(normalized))

    @staticmethod
    def _normalize_sql(sql):
        s = sql if isinstance(sql, str) else ""
        s = s.strip()
        while s.endswith(";"):
            s = s[:-1].rstrip()
        return s

    @staticmethod
    def _as_text(text):
        if isinstance(text, str):
            return text
        if isinstance(text, (list, tuple)) and text and isinstance(text[0], str):
            return text[0]
        return ""