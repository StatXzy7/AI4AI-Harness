"""Draw several SQL candidates at varied temperatures and elect the winner by execution-aware majority vote, pooling votes across queries whose result signatures match."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AGlmS0G3(SQLHarness):
    """Self-consistency voting over sampled SQL candidates.

    Control flow (a real change versus a single greedy call):

      1. SAMPLE   -- one greedy candidate plus temperature-sampled candidates
                     are drawn from the frozen solver (identical prompt).
      2. DEDUPE   -- candidates are extracted and canonicalised, so trivial
                     formatting differences collapse into a single candidate
                     that accumulates the votes of all its duplicates.
      3. EXECUTE  -- every distinct candidate is run against the database
                     (read-only statements only); each survivor earns a result
                     signature = (row count, sorted normalised rows).
      4. VOTE     -- survivors are grouped by result signature, so queries
                     that differ syntactically but answer identically pool
                     their votes; the strongest signature wins, and the most
                     frequent SQL inside that group is returned.  If nothing
                     executes, a plain text-frequency vote decides.

    Note: execution outcomes are used only to *select* among the drawn
    samples; nothing is ever fed back into a prompt, so the mechanism stays a
    pure vote (no repair loop).
    """

    SAMPLE_TEMPERATURES = (0.0, 0.6, 0.8, 0.8, 1.0)
    ROW_CAP = 200                    # max rows folded into a result signature
    READONLY_HEADS = ("select", "with", "values")

    SYSTEM = (
        "You are an expert text-to-SQL engine. Given a database schema and a "
        "question, output exactly one SQL query and nothing else."
    )

    # ---------------------------------------------------------------- entry

    def solve(self, question: str) -> str:
        q = question if isinstance(question, str) else str(question)
        prompt = self._build_prompt(q)

        # 1) draw the candidate pool
        samples = []
        for temperature in self.SAMPLE_TEMPERATURES:
            samples.extend(self._llm_texts(prompt, temperature))

        # 2) extract SQL and merge duplicates into voting candidates
        candidates = {}
        for text in samples:
            sql = self._extract(text)
            if not sql:
                continue
            norm = self._normalize(sql)
            if norm not in candidates:
                candidates[norm] = {
                    "sql": sql,
                    "votes": 0,
                    "first": len(candidates),   # order of first appearance
                    "ok": False,
                    "sig": None,
                }
            candidates[norm]["votes"] += 1

        if not candidates:
            return self._fallback(samples)

        # 3) execute every distinct candidate
        for cand in candidates.values():
            cand["ok"], cand["sig"] = self._try_execute(cand["sql"])

        # 4) vote
        return self._elect(list(candidates.values()))

    # ---------------------------------------------------------------- stage

    def _build_prompt(self, question: str) -> str:
        return (
            "Database schema:\n"
            f"{self.schema}\n\n"
            "Write ONE SQL query that answers the question.\n"
            f"Question: {question}\n\n"
            "Rules:\n"
            "- Output a single SQLite SELECT query.\n"
            "- Use only tables and columns that appear in the schema.\n"
            "- Put the query in a