"""Execution-guided self-consistency voting: draw multiple SQL samples, execute each distinct candidate, and return the query whose result set wins the most support across samples."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge

__all__ = ["P2P2AGlmS1G7"]


class P2P2AGlmS1G7(SQLHarness):
    """Multi-sample voting harness for a frozen text-to-SQL solver.

    Instead of a single greedy generation, ``solve`` runs this control flow:

    1. One greedy LLM call (temperature 0.0) anchors the candidate pool.
    2. ``TOTAL_SAMPLES - 1`` additional samples are drawn at a higher
       temperature to explore alternative readings of the question.
    3. Each *distinct* candidate SQL is executed once against the database.
    4. Candidates that execute successfully are grouped by an
       order-insensitive fingerprint of their result rows; a group's score
       is the total sampling weight of every candidate producing that
       result, so different queries that agree on the answer pool their
       votes.
    5. The highest-scoring group wins; ties prefer non-empty results and
       then the group containing the earliest (greedy) candidate. If no
       candidate executes, the greedy candidate is returned unchanged.
    """

    TOTAL_SAMPLES = 5           # 1 greedy anchor + 4 diverse samples
    DIVERSE_TEMPERATURE = 0.8   # sampling temperature for the diverse draws
    MAX_SIGNATURE_ROWS = 50     # rows per result used to build the vote fingerprint

    SYSTEM = (
        "You are an expert SQL writer. Given a database schema and a natural "
        "language question, output exactly one SQL query that answers the "
        "question. Respond with the SQL query only - no explanation, no prose."
    )

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        """Answer a question with the crowd-favourite SQL among sampled candidates."""
        question = "" if question is None else str(question)
        if not question.strip():
            return ""

        prompt = self._build_prompt(question)

        # 1-2) draw the sample pool: greedy anchor first, diverse companions after
        texts = self._generate(prompt, temperature=0.0)
        for _ in range(max(0, self.TOTAL_SAMPLES - 1)):
            texts.extend(self._generate(prompt, temperature=self.DIVERSE_TEMPERATURE))

        # 3) extract SQL, dedupe on a canonical form, keep sampling weights
        entries = []  # [sql, times_sampled] in first-appearance order
        seen = {}     # canonical sql -> index into entries
        for text in texts:
            sql = self._extract_sql(text)
            if not sql:
                continue
            key = self._canonical(sql)
            if key in seen:
                entries[seen[key]][1] += 1
            else:
                seen[key] = len(entries)
                entries.append([sql, 1])

        if not entries:
            # nothing extractable at all - degrade to the raw greedy extraction
            return self._extract_sql(texts[0]) if texts else ""

        # 4) execute every distinct candidate exactly once
        results = [self._safe_execute(sql) for sql, _ in entries]

        # 5) vote by agreement of the executed results
        groups = {}  # result signature -> [weight, nonempty, first_idx, sql]
        for idx, ((sql, times), result) in enumerate(zip(entries, results)):
            if not result.get("ok"):
                continue  # queries that fail to execute get no vote
            rows = result.get("rows") or []
            signature = self._result_signature(rows)
            if signature is None:
                signature = ("__unsignable__", idx)  # never merge incomparable results
            group = groups.setdefault(signature, [0, False, idx, sql])
            group[0] += times
            if len(rows) > 0:
                group[1] = True

        if groups:
            best = max(groups.values(), key=lambda g: (g[0], g[1], -g[2]))
            return best[3]

        # no candidate executed cleanly - keep the greedy anchor
        return entries[0][0]

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _build_prompt(self, question: str) -> str:
        """Assemble the generation prompt from the schema and the question."""
        schema = getattr(self, "schema", None) or ""
        return (
            "Database schema:\n"
            f"{schema}\n\n"
            f"Question: {question}\n\n"
            "Write one SQL query that answers the question. "
            "Respond with the SQL query only."
        )

    def _generate(self, prompt: str, temperature: float) -> list:
        """Perform one LLM call and normalise its output to a list of texts."""
        try:
            out = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
        except TypeError:
            # the bridge may not accept every keyword - retry without `n`
            try:
                out = self.llm(prompt, system=self.SYSTEM, temperature=temperature)
            except Exception:
                return []
        except Exception:
            return []
        return self._as_texts(out)

    def _extract_sql(self, text: str) -> str:
        """Pull the SQL statement out of a model response."""
        if not text:
            return ""
        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = self._strip_fences(text)
        return (sql or "").strip()

    def _safe_execute(self, sql: str) -> dict:
        """Run a candidate query, guaranteeing a dict-shaped result."""
        try:
            result = self.execute(sql)
        except Exception as exc:  # a broken query must never kill the vote
            return {"ok": False, "rows": [], "error": str(exc)}
        if not isinstance(result, dict):
            return {"ok": False, "rows": [], "error": "unexpected execute() result"}
        return result

    def _result_signature(self, rows):
        """Order-insensitive fingerprint of a result set (None if incomparable)."""
        try:
            normalised = []
            for row in list(rows)[: self.MAX_SIGNATURE_ROWS]:
                if isinstance(row, dict):
                    normalised.append(
                        ("d", tuple(sorted((str(k), repr(v)) for k, v in row.items())))
                    )
                elif isinstance(row, (list, tuple)):
                    normalised.append(("s", tuple(repr(v) for v in row)))
                else:
                    normalised.append(("o", repr(row)))
            normalised.sort()
            return tuple(normalised)
        except Exception:
            return None

    @staticmethod
    def _canonical(sql: str) -> str:
        """Whitespace-collapsed form used to dedupe equivalent candidates."""
        return " ".join((sql or "").split())

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Best-effort removal of markdown code fences."""
        t = (text or "").strip()
        if t.startswith("