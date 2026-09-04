"""Self-consistency voting: draw a greedy candidate plus several sampled candidates, execute each, and return the SQL whose execution result set wins the majority vote."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS1G5(SQLHarness):
    """Text-to-SQL harness using execution-grounded self-consistency voting.

    Improvement over a single greedy call: instead of trusting one
    generation, we draw one greedy and NUM_SAMPLES high-temperature
    candidate queries, execute them against the database, and select the
    candidate whose result set is produced by the most candidates
    (order-insensitive comparison, so queries differing only in row order
    still vote together). The greedy candidate breaks ties; if no candidate
    executes successfully we fall back to it.
    """

    NUM_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.7

    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQLite text-to-SQL translator. Given a "
            "database schema and a natural-language question, output ONLY "
            "the SQL query that answers the question: no explanation, no "
            "markdown fences, no extra text."
        )
        prompt = (
            "Database schema:\n"
            f"{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Write a single SQLite SQL query that answers the question."
        )

        candidates = []

        # Candidate 0: greedy (also serves as tie-breaker and fallback).
        greedy_sql = bridge.extract_sql(
            self.llm(prompt, system=system, temperature=0.0)
        )
        if greedy_sql:
            candidates.append(greedy_sql)

        # Candidates 1..N: sampled at higher temperature for diversity.
        sampled = self.llm(
            prompt,
            system=system,
            temperature=self.SAMPLE_TEMPERATURE,
            n=self.NUM_SAMPLES,
        )
        for text in self._as_list(sampled):
            sql = bridge.extract_sql(text)
            if sql:
                candidates.append(sql)

        if not candidates:
            return greedy_sql or ""

        return self._vote(candidates, greedy_sql)

    # ------------------------------------------------------------------
    # Voting machinery
    # ------------------------------------------------------------------

    @staticmethod
    def _as_list(result):
        """Normalize llm(n>1) output whether it returns a list or a string."""
        if isinstance(result, (list, tuple)):
            return list(result)
        return [result]

    def _vote(self, candidates, greedy_sql):
        exec_cache = {}

        def run(sql):
            if sql not in exec_cache:
                try:
                    exec_cache[sql] = self.execute(sql)
                except Exception as exc:  # one bad query must not kill voting
                    exec_cache[sql] = {
                        "ok": False,
                        "rows": [],
                        "error": str(exc),
                    }
            return exec_cache[sql]

        # Group successful candidates by canonical execution result.
        tally = {}
        for sql in candidates:
            res = run(sql)
            if not res.get("ok"):
                continue
            key = self._result_key(res.get("rows") or [])
            tally.setdefault(key, []).append(sql)

        if not tally:
            # Nothing executed cleanly: trust the greedy candidate.
            return greedy_sql or candidates[0]

        def group_score(key):
            sqls = tally[key]
            has_rows = 1 if key[1] else 0
            greedy_bonus = 1 if greedy_sql in sqls else 0
            return (len(sqls), has_rows, greedy_bonus)

        best_key = max(tally, key=group_score)
        winners = tally[best_key]
        if greedy_sql in winners:
            return greedy_sql
        return winners[0]

    @staticmethod
    def _result_key(rows):
        """Order-insensitive canonical form of a result set."""
        canon_rows = []
        for row in rows:
            if isinstance(row, (list, tuple)):
                canon_rows.append(tuple(repr(cell) for cell in row))
            else:
                canon_rows.append((repr(row),))
        return (tuple(sorted(canon_rows)), bool(rows))