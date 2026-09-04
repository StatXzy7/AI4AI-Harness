"""Self-consistency voting: draw several SQL candidates from the frozen solver, execute each one, and return the candidate whose execution result commands the largest consensus across samples."""
# MECHANISM: vote        -- you draw multiple samples and select among them

import json
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS1G3(SQLHarness):
    """Execution-grounded self-consistency over sampled SQL candidates.

    Control flow (a real change vs. a single greedy call):
      1. DRAW: the frozen solver is called TOTAL_SAMPLES times with the same
         prompt -- one greedy anchor at temperature 0.0 plus temperatured
         re-samples -- producing a pool of candidate SQL statements.
      2. TALLY: candidates are extracted, normalised and de-duplicated, with
         per-candidate sample counts kept as votes.
      3. EXECUTE: every distinct (read-only) candidate is executed once.
      4. SELECT: candidates whose executions return identical result sets are
         merged into equivalence groups; the group backed by the most samples
         wins (ties: non-empty result, then the greedy anchor, then earliest
         proposal).  If nothing executes, plain string-majority voting decides.

    The LLM is never invoked after execution and execution errors are never fed
    back, so this is purely a draw-multiple-samples-and-select mechanism.
    """

    TOTAL_SAMPLES = 6        # 1 greedy anchor + 5 temperatured samples
    SAMPLE_TEMPERATURE = 0.8
    MAX_SIG_ROWS = 100       # rows per result used to compare executions

    SYSTEM = (
        "You are a strict Text-to-SQL engine. Given a database schema and a "
        "question, reply with exactly one SQLite SELECT statement and nothing "
        "else: no explanation, no markdown, no comments."
    )

    # ------------------------------------------------------------------ API

    def solve(self, question: str) -> str:
        question = question or ""
        prompt = self._prompt(question)

        # ---- Stage 1: draw the candidate pool ---------------------------
        samples = []
        for i in range(self.TOTAL_SAMPLES):
            temperature = 0.0 if i == 0 else self.SAMPLE_TEMPERATURE
            samples.extend(self._as_texts(self._call(prompt, temperature)))

        # ---- Stage 2: extract, normalise, tally -------------------------
        votes = Counter()   # normalised SQL -> number of samples producing it
        pos = {}            # normalised SQL -> first-seen rank
        sql_of = {}         # normalised SQL -> representative SQL text
        for text in samples:
            sql = (bridge.extract_sql(text) or "").strip()
            while sql.endswith(";"):
                sql = sql[:-1].strip()
            if not sql:
                continue
            key = self._norm(sql)
            if key not in sql_of:
                sql_of[key] = sql
                pos[key] = len(pos)
            votes[key] += 1

        if not sql_of:
            # Nothing extractable anywhere: best effort is the raw greedy text.
            return samples[0].strip() if samples else ""

        order = list(sql_of)          # first-seen order; index 0 == greedy anchor
        anchor = order[0]

        # ---- Stage 3: execute each distinct candidate once --------------
        exec_ok = {}
        exec_sig = {}
        for key in order:
            sql = sql_of[key]
            ok = False
            sig = None
            if self._is_query(sql):   # never execute non-SELECT statements
                try:
                    out = self.execute(sql) or {}
                except Exception:
                    out = {}
                ok = bool(out.get("ok"))
                if ok:
                    sig = self._signature(out.get("rows"))
            exec_ok[key] = ok
            exec_sig[key] = sig

        # ---- Stage 4: vote over execution results -----------------------
        groups = {}  # result signature -> [candidate keys]
        for key in order:
            if exec_ok[key]:
                groups.setdefault(exec_sig[key], []).append(key)

        if groups:
            def group_rank(sig):
                keys = groups[sig]
                return (
                    sum(votes[k] for k in keys),   # 1) consensus weight
                    1 if sig[0] == "rows" else 0,   # 2) prefer non-empty on ties
                    1 if anchor in keys else 0,     # 3) prefer anchor's answer
                    -min(pos[k] for k in keys),     # 4) prefer earlier proposal
                )

            best_sig = max(groups, key=group_rank)
            # Any member of the winning group yields the winning result;
            # return its most frequently sampled formulation.
            best_key = max(groups[best_sig],
                           key=lambda k: (votes[k], -pos[k]))
        else:
            # Nothing executed: fall back to string-majority voting.
            best_key = max(order, key=lambda k: (votes[k], -pos[k]))

        return sql_of[best_key]

    # ------------------------------------------------------------- helpers

    def _call(self, prompt: str, temperature: float):
        try:
            return self.llm(prompt, system=self.SYSTEM,
                            temperature=temperature, n=1)
        except TypeError:
            # Bridge with a narrower signature: degrade to a bare call.
            return self.llm(prompt)

    def _prompt(self, question: str) -> str:
        schema = (getattr(self, "schema", "") or "").strip()
        return "\n".join([
            "Database schema:",
            schema or "(no schema provided)",
            "",
            "Write one SQLite SELECT statement that answers the question.",
            "Question: " + question,
            "",
            "Rules:",
            "- Output exactly one SQL statement.",
            "- No explanations, no comments, no markdown fences.",
            "- Use only tables and columns that appear in the schema.",
            "SQL:",
        ])

    # -- normalisation helpers --------------------------------------------

    @staticmethod
    def _norm(sql: str) -> str:
        return " ".join(sql.split()).lower()

    @staticmethod
    def _is_query(sql: str) -> bool:
        head = sql.lstrip().lower()
        return head.startswith(("select", "with", "values"))

    # -- result-signature helpers ------------------------------------------

    @classmethod
    def _signature(cls, rows):
        """Order-insensitive fingerprint of an execution result."""
        if rows is None:
            return ("empty",)
        rows = list(rows)[: cls.MAX_SIG_ROWS]
        if not rows:
            return ("empty",)
        width = cls._row_len(rows[0])
        counts = Counter(cls._freeze(cls._row_values(r)) for r in rows)
        packed = tuple(sorted((repr(token), c) for token, c in counts.items()))
        return ("rows", width, packed)

    @staticmethod
    def _row_values(row):
        # Dict rows are reduced to their values (in query order) so that mere
        # alias differences do not split otherwise identical executions.
        if isinstance(row, dict):
            return tuple(row.values())
        if isinstance(row, (list, tuple)):
            return tuple(row)
        return (row,)

    @