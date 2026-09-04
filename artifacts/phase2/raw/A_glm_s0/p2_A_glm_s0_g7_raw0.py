"""Vote by execution: draw multiple SQL candidates from the frozen solver, execute every distinct candidate, and return the candidate whose execution result is backed by the most samples."""

# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS0G7(SQLHarness):
    """Execution-grounded self-consistency voting over sampled SQL candidates.

    Improvement over a single greedy call:

    1. Candidate generation -- one greedy anchor (temperature 0.0) plus one
       sample per temperature in ``SAMPLE_TEMPERATURES`` (5 more calls).
    2. Execution -- every *distinct* candidate SQL string is run against the
       database via ``self.execute``.
    3. Voting -- candidates are clustered by execution fingerprint (result
       columns, row contents, row count).  A cluster's weight is the number of
       samples whose SQL produced that result, so differently-written but
       semantically equivalent queries pool their support.
    4. Selection -- the heaviest successfully-executing cluster wins (exact
       ties prefer clusters that actually return rows); within the winning
       cluster the most frequently sampled, then shortest, SQL is returned.
    5. Fallback -- if nothing executes, a plain plurality vote over the raw
       candidate strings decides.
    """

    SAMPLE_TEMPERATURES = (0.6, 0.7, 0.8, 0.9, 1.0)  # one sample per value
    MAX_EXECUTE = 8        # safety cap on distinct SQL strings executed
    MAX_SIG_ROWS = 50      # rows per result used when fingerprinting

    SYSTEM_PROMPT = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "question, write exactly one SQLite query that answers the question. "
        "Reply with the SQL query only."
    )

    # --------------------------------------------------------------- solve

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        prompt = self._build_prompt(question)

        # -- stage 1: draw candidates (greedy anchor + temperature ladder) ---
        counts = {}   # normalized sql -> number of samples producing it
        order = []    # distinct candidates, first-seen order

        anchor_texts = self._call(prompt, temperature=0.0)
        for text in anchor_texts:
            self._tally(text, counts, order)
        for temp in self.SAMPLE_TEMPERATURES:
            for text in self._call(prompt, temperature=temp):
                self._tally(text, counts, order)

        if not order:
            # Nothing survived SQL extraction: return the raw greedy text.
            return anchor_texts[0].strip() if anchor_texts else ""
        if len(order) == 1:
            # Solver was fully deterministic: nothing to vote between.
            return order[0]

        # -- stage 2: execute distinct candidates, best-supported first ------
        ranked = sorted(range(len(order)), key=lambda i: (-counts[order[i]], i))
        exec_fp = {}
        for i in ranked[: self.MAX_EXECUTE]:
            exec_fp[order[i]] = self._fingerprint(self._execute(order[i]))

        # -- stage 3: vote over execution-result clusters ---------------------
        cluster_weight = {}    # fingerprint -> total supporting samples
        cluster_members = {}   # fingerprint -> {sql: supporting samples}
        for sql, c in counts.items():
            fp = exec_fp.get(sql)
            if fp is None:     # not executed (cap reached) or execution failed
                continue
            cluster_weight[fp] = cluster_weight.get(fp, 0) + c
            members = cluster_members.setdefault(fp, {})
            members[sql] = members.get(sql, 0) + c

        if cluster_weight:
            # Heaviest cluster wins; exact ties prefer clusters that return at
            # least one row (guards against over-constrained SQL).
            best_fp = max(
                cluster_weight, key=lambda fp: (cluster_weight[fp], fp[-1] > 0)
            )
            members = cluster_members[best_fp]
            return max(members, key=lambda s: (members[s], -len(s)))

        # -- stage 4: nothing executed -> plurality over raw SQL strings ------
        return max(counts, key=lambda s: (counts[s], -len(s)))

    # ------------------------------------------------------------- helpers

    def _build_prompt(self, question: str) -> str:
        schema = (self.schema or "").strip() or "(no schema provided)"
        return (
            "Database schema:\n"
            f"{schema}\n\n"
            "Write exactly one SQLite query that answers the question.\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Select only the columns needed to answer the question.\n"
            "- Output the SQL query only, nothing else.\n\n"
            f"Question: {question}\n"
            "SQL:"
        )

    def _call(self, prompt: str, temperature: float):
        """One solver call at ``temperature``; result normalized to [str, ...]."""
        try:
            out = self.llm(
                prompt, system=self.SYSTEM_PROMPT, temperature=temperature, n=1
            )
        except TypeError:
            # Solver rejected the ``n`` keyword: retry without it.
            out = self.llm(prompt, system=self.SYSTEM_PROMPT, temperature=temperature)
        if out is None:
            return []
        if isinstance(out, str):
            return [out]
        return [t if isinstance(t, str) else str(t) for t in out]

    def _tally(self, text, counts, order):
        """Extract and normalize one sample's SQL, then record its vote."""
        sql = self._extract_sql(text)
        if not sql:
            return
        if sql not in counts:
            counts[sql] = 0
            order.append(sql)
        counts[sql] += 1

    @staticmethod
    def _extract_sql(text) -> str:
        try:
            sql = bridge.extract_sql(text or "")
        except Exception:
            sql = text or ""
        # Collapse whitespace so trivially different strings pool together.
        return " ".join(str(sql).split())

    def _execute(self, sql: str) -> dict:
        try:
            return self.execute(sql) or {}
        except Exception as exc:  # never let one bad query kill the vote
            return {"ok": False, "rows": [], "error": str(exc)}

    def _fingerprint(self, result):
        """Hashable signature of an execution result; None if it failed."""
        if not isinstance(result, dict) or not result.get("ok"):
            return None
        rows = list(result.get("rows") or [])
        head = tuple(repr(r) for r in rows[: self.MAX_SIG_ROWS])
        cols = result.get("columns")
        cols_key = (
            tuple(str(c) for c in cols) if isinstance(cols, (list, tuple)) else ()
        )
        return (cols_key, head, len(rows))