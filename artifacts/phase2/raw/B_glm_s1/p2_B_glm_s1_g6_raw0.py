"""Execution-validated self-consistency voting: one greedy plus several sampled SQL candidates are generated, each distinct candidate is executed against the database, and the candidate whose result set collects the most votes is returned."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS1G6(SQLHarness):
    """Vote over sampled candidates using execution results as ballots.

    Control flow per question:

    1. A greedy LLM call (temperature 0) anchors the candidate pool.
    2. ``NUM_SAMPLES`` further calls at temperature ``SAMPLE_TEMP``
       diversify the pool; identical generations are kept, because
       duplicates are votes.
    3. Every distinct read-only candidate is executed once against the
       database (outcomes are cached per canonical SQL string).
    4. Candidates that execute cleanly are clustered by a fingerprint of
       what they *return* (row count, row multiset, first row), and the
       biggest cluster wins.  Voting on results rather than on surface
       SQL form lets semantically equivalent queries pool their votes.
    5. If no candidate executes, a hotter resampling round re-runs the
       election; failing that, the plurality raw proposal is returned.
    """

    SYSTEM = (
        "You are an expert SQLite data analyst. Given a database schema and "
        "a natural-language question, reply with exactly one syntactically "
        "valid SQLite SELECT query and nothing else."
    )

    NUM_SAMPLES = 4      # sampled candidates in the first voting round
    RETRY_SAMPLES = 4    # extra candidates in the fallback round
    SAMPLE_TEMP = 0.8
    RETRY_TEMP = 1.0
    SIG_ROW_CAP = 50     # rows inspected when fingerprinting a result set

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        exec_cache = {}

        # Round 1: greedy anchor + diverse samples from the same prompt.
        candidates = []
        greedy = self._call(prompt, 0.0)
        if greedy:
            candidates.append(greedy)
        for _ in range(self.NUM_SAMPLES):
            cand = self._call(prompt, self.SAMPLE_TEMP)
            if cand:
                candidates.append(cand)

        winner = self._elect(candidates, exec_cache)
        if winner is not None:
            return winner

        # Round 2: nothing executed cleanly -- resample hotter, vote again.
        for _ in range(self.RETRY_SAMPLES):
            cand = self._call(prompt, self.RETRY_TEMP)
            if cand:
                candidates.append(cand)

        winner = self._elect(candidates, exec_cache)
        if winner is not None:
            return winner

        # Last resort: plurality over the raw proposals, execution-free.
        return self._plurality(candidates)

    # ------------------------------------------------------------------ #
    # candidate generation
    # ------------------------------------------------------------------ #

    def _build_prompt(self, question: str) -> str:
        schema = self.schema.strip() if isinstance(self.schema, str) else ""
        return (
            "Database schema:\n"
            "----------------\n"
            f"{schema}\n\n"
            "Task:\n"
            "------\n"
            "Write ONE SQLite query that answers the question.\n"
            "- Use only tables and columns that appear in the schema above.\n"
            "- Emit a single SELECT statement (a WITH ... SELECT is fine).\n"
            "- Output only the SQL: no explanation, no markdown, no comment.\n\n"
            f"Question: {question.strip()}\n\n"
            "SQL:"
        )

    def _call(self, prompt: str, temperature: float) -> str:
        """One LLM call -> extracted, whitespace-normalised SQL ('' on failure)."""
        try:
            out = self.llm(
                prompt, system=self.SYSTEM, temperature=temperature, n=1
            )
        except TypeError:
            # Very defensive: the frozen solver may not forward every kwarg.
            out = self.llm(prompt, system=self.SYSTEM, temperature=temperature)
        except Exception:
            return ""
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        if not isinstance(out, str):
            out = str(out)
        try:
            sql = bridge.extract_sql(out)
        except Exception:
            return ""
        return self._canon(sql)

    # ------------------------------------------------------------------ #
    # voting machinery
    # ------------------------------------------------------------------ #

    def _elect(self, candidates, exec_cache):
        """Return the SQL with the strongest execution-result vote, else None.

        ``candidates`` is a list of canonical SQL strings; ``exec_cache``
        memoises ``sql -> (ok, signature)`` across voting rounds.
        """
        clusters = {}
        for idx, sql in enumerate(candidates):
            if not sql or not self._is_readonly(sql):
                continue
            if sql not in exec_cache:
                ok, rows = self._run(sql)
                if ok:
                    exec_cache[sql] = (True, self._sig(rows))
                else:
                    exec_cache[sql] = (False, None)
            ok, sig = exec_cache[sql]
            if ok:
                clusters.setdefault(sig, []).append((idx, sql))

        if not clusters:
            return None

        # Biggest cluster wins; ties go to the cluster containing the
        # earliest proposal (which favours the greedy anchor).
        best_group = max(
            clusters.values(),
            key=lambda group: (len(group), -min(idx for idx, _ in group)),
        )

        # Inside the winning cluster the most frequent exact SQL is the
        # representative; ties favour the earliest, then the shortest.
        counts = {}
        for idx, sql in best_group:
            counts.setdefault(sql, []).append(idx)
        return max(
            counts.items(),
            key=lambda kv: (len(kv[1]), -kv[1][0], -len(kv[0])),
        )[0]

    def _plurality(self, candidates):
        """Fallback when nothing executes: most frequent raw proposal."""
        counts = {}
        for idx, sql in enumerate(candidates):
            if sql:
                counts.setdefault(sql, []).append(idx)
        if not counts:
            return candidates[0] if candidates else ""
        return max(counts.items(), key=lambda kv: (len(kv[1]), -kv[1][0]))[0]

    # ------------------------------------------------------------------ #
    # execution plumbing
    # ------------------------------------------------------------------ #

    def _run(self, sql):
        """Execute ``sql``; return (True, rows) on success else (False, None)."""
        try:
            res = self.execute(sql)
        except Exception:
            return False, None
        if not isinstance(res, dict) or not res.get("ok"):
            return False, None
        rows = res.get("rows")
        if not isinstance(rows, (list, tuple)):
            rows = []
        return True, list(rows)

    @classmethod
    def _sig(cls, rows):
        """Fingerprint a result set: size, row multiset (capped), first row."""
        try:
            head = sorted(repr(r) for r in rows[: cls.SIG_ROW_CAP])
            first = repr(rows[0]) if rows else None
            return (len(rows), tuple(head), first)
        except Exception:
            return ("opaque",)

    # ------------------------------------------------------------------ #
    # small utilities
    # ------------------------------------------------------------------ #

    @staticmethod
    def _canon(sql):
        """Collapse whitespace and drop trailing semicolons; keep case intact."""
        s = " ".join(str(sql or "").split())
        while s.endswith(";"):
            s = s[:-1].rstrip()
        return s

    @staticmethod
    def _is_readonly(sql):
        """Only SELECT / WITH statements are ever executed against the DB."""
        head = sql.lstrip().lower()
        return head.startswith("select") or head.startswith("with")