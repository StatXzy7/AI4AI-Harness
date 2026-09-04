"""Self-consistency voting harness: sample several candidate SQL queries, execute each one, and return the query whose execution result wins a majority vote over result-set equivalence classes."""
# MECHANISM: vote        -- you draw multiple samples and select among them

import collections

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BKimiS2G2(SQLHarness):
    """Execution-grounded self-consistency for Text-to-SQL.

    A single greedy decode is fragile: one wrong token can break the query.
    Instead we draw one greedy sample plus several diverse samples, deduplicate
    the extracted SQL, execute each unique candidate, and cluster the ones that
    run by their (order-insensitive) result sets. Each sample casts a weighted
    vote for its result cluster, and the SQL from the winning cluster is
    returned. Clusters with empty result sets are only considered when every
    executable candidate returns empty. If nothing executes at all, we fall
    back to the greedy candidate.
    """

    NUM_DIVERSE_SAMPLES = 4
    SAMPLE_TEMPERATURE = 0.7

    def _build_prompt(self, question: str) -> str:
        return (
            "You are given a relational database schema and a natural-language "
            "question. Write a single SQL query that answers the question using "
            "only tables and columns that appear in the schema.\n\n"
            f"### Schema\n{self.schema}\n\n"
            f"### Question\n{question}\n\n"
            "Respond with ONLY the SQL query: no explanation, no comments, "
            "no markdown fences."
        )

    @staticmethod
    def _as_text(raw) -> str:
        """The llm() helper may return a string or a list of strings."""
        if isinstance(raw, (list, tuple)):
            return str(raw[0]) if raw else ""
        return str(raw)

    @staticmethod
    def _signature(rows):
        """Canonical, order-insensitive signature of a result set."""
        try:
            norm = []
            for row in rows:
                if isinstance(row, dict):
                    cells = tuple(row[k] for k in sorted(row))
                elif isinstance(row, (list, tuple)):
                    cells = tuple(row)
                else:
                    cells = (row,)
                norm.append(tuple(str(c) for c in cells))
            return tuple(sorted(norm))
        except Exception:
            return None

    def solve(self, question: str) -> str:
        prompt = self._build_prompt(question)
        system = "You are an expert Text-to-SQL translator. Output only SQL."

        # 1) Draw multiple samples: one greedy + several diverse ones.
        texts = [self._as_text(self.llm(prompt, system=system,
                                        temperature=0.0, n=1))]
        for _ in range(self.NUM_DIVERSE_SAMPLES):
            texts.append(self._as_text(self.llm(prompt, system=system,
                                                temperature=self.SAMPLE_TEMPERATURE,
                                                n=1)))

        # 2) Extract SQL and tally sample frequency per unique query,
        #    preserving first-occurrence order (greedy first).
        freq = collections.OrderedDict()
        for t in texts:
            sql = (bridge.extract_sql(t) or "").strip()
            if sql:
                freq[sql] = freq.get(sql, 0) + 1

        if not freq:
            return ""

        # 3) Execute each unique candidate once and cluster by result signature.
        #    signature -> {"votes": int, "sql": str, "empty": bool}
        clusters = collections.OrderedDict()
        for sql, weight in freq.items():
            try:
                res = self.execute(sql)
            except Exception:
                continue
            if not res or not res.get("ok"):
                continue
            rows = res.get("rows") or []
            sig = self._signature(rows)
            if sig is None:
                sig = ("__unhashable__", sql)
            if sig in clusters:
                clusters[sig]["votes"] += weight
            else:
                clusters[sig] = {"votes": weight, "sql": sql, "empty": len(rows) == 0}

        # 4) Vote. Prefer non-empty result clusters when any exist.
        if clusters:
            pool = [c for c in clusters.values() if not c["empty"]] or list(clusters.values())
            best = max(pool, key=lambda c: c["votes"])
            return best["sql"]

        # 5) Nothing executed successfully: fall back to the most frequent
        #    (greedy-first, on ties) candidate.
        return max(freq.items(), key=lambda kv: kv[1])[0]