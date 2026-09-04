"""Draw multiple SQL candidates at varied temperatures, execute each one against the database, and vote on agreeing result sets to select the final query."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2AGlmS2G2"]


class P2P2AGlmS2G2(SQLHarness):
    """Execution-validated self-consistency voting over sampled SQL candidates.

    Control flow (a real change versus a single greedy call):

      1. DRAW     - one greedy anchor candidate plus several temperature-sampled
                    candidates are generated for the same prompt.
      2. DEDUP    - candidates are canonicalised and deduplicated so every
                    distinct query is executed at most once.
      3. EXECUTE  - each distinct candidate is run against the database.
      4. VOTE     - candidates that execute successfully cast ballots for their
                    result signature (row count + leading row contents); the
                    signature with the largest vote total wins and the earliest
                    query producing it (greedy-first) is returned. If no
                    candidate executes, a plain majority vote over the
                    canonical query text decides.
    """

    NAME = "P2P2AGlmS2G2"

    #: Sampling ladder; the first entry is the greedy anchor.
    TEMPERATURES = (0.0, 0.4, 0.7, 0.9, 1.0)

    #: Number of leading rows used to fingerprint a result set.
    SIGNATURE_ROW_CAP = 50

    SYSTEM = (
        "You are an expert SQLite programmer. Using only the schema provided, "
        "translate the question into exactly one SQL SELECT query. "
        "Respond with the SQL query and nothing else."
    )

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)

        # -- 1. draw candidates ------------------------------------------ #
        samples = self._draw_candidates(prompt)
        if not samples:
            return self._last_resort(prompt)

        # -- 2. canonical dedup + vote tallies --------------------------- #
        counts = {}      # canonical key -> number of samples producing it
        first_idx = {}   # canonical key -> earliest sample index
        rep_sql = {}     # canonical key -> representative SQL text
        for idx, sql in samples:
            key = self._canonical(sql)
            counts[key] = counts.get(key, 0) + 1
            if key not in first_idx:
                first_idx[key] = idx
                rep_sql[key] = sql

        # -- 3. execute each distinct candidate exactly once ------------- #
        outcomes = {}
        for key in sorted(rep_sql, key=lambda k: first_idx[k]):
            outcomes[key] = self._safe_execute(rep_sql[key])

        # -- 4a. vote by result signature among executing candidates ----- #
        groups = {}  # result signature -> list of canonical keys
        for key, outcome in outcomes.items():
            if outcome.get("ok"):
                sig = self._result_signature(outcome.get("rows"))
                groups.setdefault(sig, []).append(key)

        if groups:
            best_sig = max(
                groups,
                key=lambda sig: (
                    sum(counts[k] for k in groups[sig]),       # vote total
                    -min(first_idx[k] for k in groups[sig]),   # greedy-first
                ),
            )
            winner = min(groups[best_sig], key=lambda k: first_idx[k])
            return rep_sql[winner]

        # -- 4b. nothing executed: majority vote on the query text ------- #
        best_key = max(counts, key=lambda k: (counts[k], -first_idx[k]))
        return rep_sql[best_key]

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    def _draw_candidates(self, prompt):
        """Generate one candidate per temperature on the sampling ladder."""
        samples = []
        for idx, temp in enumerate(self.TEMPERATURES):
            try:
                text = self.llm(prompt, system=self.SYSTEM, temperature=temp, n=1)
            except Exception:
                continue
            sql = self._extract(text)
            if sql:
                samples.append((idx, sql))
        return samples

    def _last_resort(self, prompt):
        """Single unconstrained retry when every sampled call failed."""
        try:
            text = self.llm(prompt, system=self.SYSTEM, temperature=0.0, n=1)
            return self._extract(text)
        except Exception:
            return ""

    @staticmethod
    def _extract(text):
        if text is None:
            return ""
        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""
        if not isinstance(text, str):
            text = str(text)
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = text
        if not isinstance(sql, str):
            return ""
        return sql.strip()

    def _safe_execute(self, sql):
        """Run the executor, converting any blow-up into a failed outcome."""
        try:
            outcome = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}
        if not isinstance(outcome, dict):
            return {"ok": False, "rows": [], "error": "unexpected executor return"}
        return outcome

    @staticmethod
    def _canonical(sql):
        """Normalise a query for deduplication and textual voting."""
        s = " ".join(sql.split())
        s = s.rstrip(";").strip()
        return s.lower()

    def _result_signature(self, rows):
        """Fingerprint a result set so equivalent outputs can be voted on."""
        if rows is None:
            return ("empty-result",)
        try:
            n = len(rows)
        except TypeError:
            return ("opaque", str(rows)[:200])
        head = tuple(self._row_key(row) for row in rows[: self.SIGNATURE_ROW_CAP])
        return ("rows", n, head)

    @staticmethod
    def _row_key(row):
        if isinstance(row, dict):
            return tuple(sorted(
                (str(k), "NULL" if v is None else str(v))
                for k, v in row.items()
            ))
        if isinstance(row, (list, tuple)):
            return tuple("NULL" if v is None else str(v) for v in row)
        return ("NULL" if row is None else str(row),)

    def _build_prompt(self, question):
        schema = (getattr(self, "schema", "") or "").strip()
        q = (question or "").strip()
        return (
            "Database schema:\n"
            "----------------\n"
            f"{schema}\n\n"
            f"Question: {q}\n\n"
            "Instructions:\n"
            "- Produce exactly one SQL SELECT query that answers the question.\n"
            "- Use only tables and columns from the schema above.\n"
            "- Do not explain; output only the SQL query."
        )