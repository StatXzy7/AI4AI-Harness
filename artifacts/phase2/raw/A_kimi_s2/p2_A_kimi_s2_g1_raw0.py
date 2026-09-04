"""Samples multiple candidate SQL queries and selects the winner by execution validity plus result-set majority voting."""
# MECHANISM: vote        -- you draw multiple samples and select among them

from ..harness_base import SQLHarness
from .. import bridge

SYSTEM_PROMPT = (
    "You are an expert SQLite text-to-SQL assistant. Given a database schema "
    "and a natural-language question, you output exactly one valid SQLite SQL "
    "query. Output only the SQL: no explanations, no markdown fences."
)


class P2P2AKimiS2G1(SQLHarness):
    """Self-consistency style harness: sample, execute, and vote on results."""

    SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.7

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        raw_outputs = self._sample(prompt)
        candidates = self._extract_candidates(raw_outputs)
        if not candidates:
            # Extraction failed for every sample: one greedy fallback call.
            fallback = self.llm(prompt, system=SYSTEM_PROMPT, temperature=0.0, n=1)
            sql = bridge.extract_sql(self._as_text(fallback))
            return sql or "SELECT 1"
        return self._elect(candidates)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite query that answers the question."
        )

    def _sample(self, prompt: str) -> list:
        """Draw SAMPLES completions, preferring one batched n>1 call."""
        try:
            out = self.llm(
                prompt,
                system=SYSTEM_PROMPT,
                temperature=self.SAMPLE_TEMPERATURE,
                n=self.SAMPLES,
            )
            return self._as_list(out)
        except TypeError:
            # Backend does not support n>1: fall back to separate calls.
            return [
                self.llm(
                    prompt,
                    system=SYSTEM_PROMPT,
                    temperature=self.SAMPLE_TEMPERATURE,
                )
                for _ in range(self.SAMPLES)
            ]

    @staticmethod
    def _as_text(out) -> str:
        if isinstance(out, str):
            return out
        if isinstance(out, (list, tuple)) and out:
            return str(out[0])
        return str(out)

    @classmethod
    def _as_list(cls, out) -> list:
        if isinstance(out, str):
            return [out]
        if isinstance(out, (list, tuple)):
            return [cls._as_text(o) for o in out]
        return [str(out)]

    def _extract_candidates(self, raw_outputs: list) -> list:
        """Extract SQL from each sample and drop duplicates."""
        seen = set()
        candidates = []
        for text in raw_outputs:
            sql = bridge.extract_sql(text)
            if not sql:
                continue
            norm = " ".join(sql.split()).strip().rstrip(";").lower()
            if norm in seen:
                continue
            seen.add(norm)
            candidates.append(sql.strip())
        return candidates

    @staticmethod
    def _signature(rows) -> str:
        """Order-insensitive fingerprint of a result set."""
        try:
            return repr(sorted(repr(r) for r in rows))
        except Exception:
            return repr(rows)

    def _elect(self, candidates: list) -> str:
        """Execute candidates and majority-vote on their result sets."""
        votes = {}  # signature -> {"count", "sql", "nrows"}
        for sql in candidates:
            result = self.execute(sql)
            if not result.get("ok"):
                continue
            rows = result.get("rows") or []
            sig = self._signature(rows)
            entry = votes.get(sig)
            if entry is None:
                votes[sig] = {"count": 1, "sql": sql, "nrows": len(rows)}
            else:
                entry["count"] += 1

        if not votes:
            # No candidate executed successfully: return first parseable SQL.
            return candidates[0]

        # Majority of agreeing result sets wins; ties break toward non-empty
        # result sets, then toward the shorter (usually simpler) query.
        best = max(
            votes.values(),
            key=lambda e: (e["count"], e["nrows"] > 0, -len(e["sql"])),
        )
        return best["sql"]