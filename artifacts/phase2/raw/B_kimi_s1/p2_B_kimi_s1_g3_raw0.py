"""Execution-guided self-consistency: sample several diverse candidate SQL queries, execute each distinct one, and return the query whose normalized result set wins the majority vote."""
# MECHANISM: vote        -- you draw multiple samples and select among them
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS1G3(SQLHarness):
    """Self-consistency voting over multiple sampled SQL candidates.

    Improvement over a single greedy generation: draw several diverse
    samples at a non-zero temperature, execute each distinct candidate once,
    group the candidates by their (order-normalized) execution results, and
    return the candidate whose result set is the modal one. Queries that
    fail to execute only win if every candidate fails, in which case a
    single greedy last-resort generation is attempted.
    """

    NUM_SAMPLES = 5
    SAMPLE_TEMPERATURE = 0.7

    SYSTEM = (
        "You are an expert Text-to-SQL system. Given a database schema and a "
        "natural-language question, write a single correct SQL query that "
        "answers the question. Output only the SQL query, with no explanation."
    )

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)

        # ---- Step 1: draw multiple diverse samples. ----
        sampled = []
        for _ in range(self.NUM_SAMPLES):
            text = self._generate(prompt, temperature=self.SAMPLE_TEMPERATURE)
            sql = bridge.extract_sql(text)
            if sql and sql.strip():
                sampled.append(sql.strip())

        if not sampled:
            return self._greedy_fallback(prompt)

        # ---- Step 2: tally exact-string votes; execute each distinct SQL once. ----
        counts = {}
        first_seen = {}
        results = {}
        for i, sql in enumerate(sampled):
            counts[sql] = counts.get(sql, 0) + 1
            first_seen.setdefault(sql, i)
        for sql in counts:
            results[sql] = self._run(sql)

        # ---- Step 3: group by normalized result set and elect the winner. ----
        groups = {}
        for sql, n in counts.items():
            ok, rows = results[sql]
            # Failed executions are not merged with each other: an error is
            # not evidence that two queries are equivalent.
            key = ("ok", self._freeze_rows(rows)) if ok else ("err", sql)
            g = groups.setdefault(
                key, {"ok": ok, "votes": 0, "nonempty": False, "members": []}
            )
            g["votes"] += n
            g["nonempty"] = g["nonempty"] or bool(rows)
            g["members"].append(sql)

        def group_score(item):
            _key, g = item
            return (1 if g["ok"] else 0, g["votes"], 1 if g["nonempty"] else 0)

        best = max(groups.items(), key=group_score)[1]
        best_sql = max(best["members"], key=lambda s: (counts[s], -first_seen[s]))

        if not best["ok"]:
            # Nothing executed successfully: one greedy last resort.
            greedy = self._greedy_fallback(prompt)
            if greedy:
                return greedy
        return best_sql

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        return (
            "Database schema:\n"
            + schema
            + "\n\nQuestion: "
            + question
            + "\n\nWrite one SQL query that answers the question. "
            "Return only the SQL query."
        )

    def _generate(self, prompt: str, temperature: float) -> str:
        try:
            out = self.llm(prompt, system=self.SYSTEM, temperature=temperature, n=1)
        except TypeError:
            out = self.llm(prompt)
        if isinstance(out, (list, tuple)):
            out = out[0] if out else ""
        return out if isinstance(out, str) else str(out)

    def _greedy_fallback(self, prompt: str) -> str:
        text = self._generate(prompt, temperature=0.0)
        sql = bridge.extract_sql(text)
        return (sql or "").strip()

    def _run(self, sql: str):
        try:
            res = self.execute(sql)
        except Exception:
            return False, []
        if not isinstance(res, dict) or not res.get("ok"):
            return False, []
        rows = res.get("rows")
        if rows is None:
            rows = []
        elif not isinstance(rows, list):
            rows = [rows]
        return True, rows

    @staticmethod
    def _freeze_rows(rows):
        """Canonical, row-order-insensitive fingerprint of a result set."""
        try:
            items = []
            for r in rows:
                if isinstance(r, dict):
                    items.append(
                        tuple(sorted((str(k), repr(v)) for k, v in r.items()))
                    )
                elif isinstance(r, (list, tuple)):
                    items.append(tuple(repr(v) for v in r))
                else:
                    items.append(repr(r))
            return tuple(sorted(items))
        except Exception:
            return repr(rows)