"""Draws several temperature-sampled SQL candidates from the frozen solver and returns the one whose execution result set wins a plurality vote among the executable candidates."""

# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS2G1(SQLHarness):
    """Execution-validated plurality voting over sampled SQL candidates.

    Control flow per call to ``solve`` (a real change from a single greedy call):

      1. SAMPLE: one LLM request with ``n = SAMPLES`` at nonzero temperature
         produces several candidate answers; each is reduced to a SQL string
         with ``bridge.extract_sql`` and whitespace-normalized.
      2. VALIDATE: every *distinct* candidate is executed exactly once against
         the database; candidates whose execution fails are discarded.
      3. VOTE: the surviving candidates are clustered by the signature of their
         result set (row count + contents, capped), and the cluster that
         accumulates the most votes wins; a representative SQL from that
         cluster is returned.
      4. FALLBACK: if no candidate executes at all, the most frequent candidate
         text is returned (plain text-majority vote).
    """

    SAMPLES = 6              # candidates drawn per question
    TEMPERATURE = 0.8        # nonzero so the samples actually differ
    MAX_SIGNATURE_ROWS = 50  # rows considered when comparing result sets

    SYSTEM = (
        "You are a careful text-to-SQL engine. Given a database schema and a "
        "question, output exactly one SQLite query that answers it. Output "
        "only the SQL, with no explanation."
    )

    PROMPT = """You are given the schema of a SQLite database and one question.

Schema:
{schema}

Question: {question}

Write one SQL query that answers the question.
Rules:
- Use only tables and columns that appear in the schema.
- Return exactly one query, terminated by a semicolon.
- Output nothing except the query.

SQL:"""

    # ------------------------------------------------------------------ solve

    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", None) or "(no schema provided)"
        prompt = self.PROMPT.format(schema=schema, question=question or "")

        # Step 1: draw the candidate pool.
        candidates = self._candidates(self._sample(prompt, self.TEMPERATURE, self.SAMPLES))

        # Rare fallback: extraction produced nothing usable from any sample.
        if not candidates:
            candidates = self._candidates(self._sample(prompt, 0.0, 1))

        if not candidates:
            return ""

        # Steps 2-4: validate, cluster by result, and elect.
        return self._elect(candidates)

    # -------------------------------------------------------------- sampling

    def _sample(self, prompt, temperature, n):
        """Draw ``n`` raw samples from the frozen solver."""
        try:
            out = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=n)
        except TypeError:
            # ``llm`` does not accept ``n``: emulate it with repeated calls.
            out = [
                self.llm(prompt, system=self.SYSTEM, temperature=temperature)
                for _ in range(n)
            ]
        return self._flatten(out)

    @staticmethod
    def _flatten(out):
        """Normalize an LLM response into a flat list of sample strings."""
        if out is None:
            return []
        if isinstance(out, (list, tuple)):
            flat = []
            for item in out:
                flat.extend(P2P2BGlmS2G1._flatten(item))
            return flat
        return [str(out)]

    def _candidates(self, samples):
        """Extract and normalize a SQL candidate from each raw sample."""
        out = []
        for text in samples:
            try:
                sql = bridge.extract_sql(text)
            except Exception:
                continue
            if sql and sql.strip():
                out.append(self._normalize(sql))
        return out

    @staticmethod
    def _normalize(sql):
        """Canonicalize a candidate so equal queries compare equal."""
        return " ".join(sql.strip().rstrip(";").strip().split())

    # -------------------------------------------------------------- election

    def _elect(self, candidates):
        """Validate every distinct candidate once, then vote on results."""
        # Step 2: execute each distinct candidate exactly once (cache).
        results = {}
        for sql in candidates:
            if sql not in results:
                results[sql] = self._run(sql)

        # Step 3: plurality vote over result-set signatures of the candidates
        # that executed successfully. Ties go to the earliest-seen signature.
        tally = {}
        best_count, best_sql = -1, None
        for sql in candidates:
            res = results[sql]
            if not res.get("ok"):
                continue
            sig = self._signature(res.get("rows"))
            entry = tally.setdefault(sig, [0, sql])
            entry[0] += 1
            if entry[0] > best_count:
                best_count, best_sql = entry[0], entry[1]

        if best_sql is not None:
            return best_sql

        # Step 4: nothing executed -- fall back to a text-majority vote.
        counts = {}
        best_count, best_sql = 0, candidates[0]
        for sql in candidates:
            counts[sql] = counts.get(sql, 0) + 1
            if counts[sql] > best_count:
                best_count, best_sql = counts[sql], sql
        return best_sql

    # -------------------------------------------------------------- execution

    def _run(self, sql):
        """Execute a candidate defensively; always return a result dict."""
        try:
            res = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": None, "error": str(exc)}
        if not isinstance(res, dict):
            return {"ok": False, "rows": None, "error": "unexpected execute() result"}
        if not res.get("ok"):
            return {"ok": False, "rows": None, "error": str(res.get("error", ""))}
        return res

    def _signature(self, rows):
        """A hashable fingerprint of a result set, used to cluster votes."""
        if rows is None:
            return ("no-rows-object",)
        try:
            rows = list(rows)
        except Exception:
            return ("unenumerable-rows",)
        trimmed = rows[: self.MAX_SIGNATURE_ROWS]
        try:
            norm = tuple(
                tuple(row) if isinstance(row, (list, tuple)) else (row,)
                for row in trimmed
            )
            # Keep the full row count so truncated large results still differ.
            return (len(rows), repr(norm))
        except Exception:
            return ("unsignable-rows", len(trimmed))