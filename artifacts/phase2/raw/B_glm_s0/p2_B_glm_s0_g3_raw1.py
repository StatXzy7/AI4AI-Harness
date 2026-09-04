"""Execution-guided self-consistency voting: draw several SQL candidates from the frozen solver, execute each distinct candidate, and return the query whose result set earns the most sample votes."""

# MECHANISM: vote

from collections import OrderedDict
from typing import Dict, List, Tuple

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BGlmS0G3(SQLHarness):
    """Self-consistency over SQL samples, scored by execution agreement.

    Control flow (a real change versus a single greedy call):

      1. Sample K candidate queries from the frozen solver: one greedy anchor
         (temperature 0.0) plus K-1 temperature samples with light prompt
         nudges, stopping early once three samples agree exactly.
      2. Normalize and deduplicate the candidates.
      3. Execute every distinct read-only candidate against the database.
      4. Cluster executable candidates by a canonicalized result-set
         signature; each cluster scores the number of samples that produced
         it.  The winner is the highest-scoring cluster (ties prefer
         non-empty results, then earlier samples) and its earliest
         representative SQL is returned.
      5. If no candidate executes, fall back to plurality voting over the
         SQL text itself.
    """

    SAMPLES = 5
    EARLY_STOP_AGREEMENT = 3
    SAMPLE_TEMPERATURE = 0.8
    SIGNATURE_ROW_LIMIT = 100

    SAMPLE_NUDGES = (
        "Keep the query as simple as possible.",
        "Double-check join and filter conditions.",
        "Be careful about aggregation and grouping.",
        "Prefer explicit column names over SELECT *.",
    )

    SYSTEM_PROMPT = (
        "You are a precise Text-to-SQL engine. Given a database schema and a "
        "question, output exactly one SQLite SELECT statement that answers the "
        "question. Output SQL only: no prose, no markdown fences, no explanation."
    )

    # ------------------------------------------------------------------ #
    # entry point                                                        #
    # ------------------------------------------------------------------ #

    def solve(self, question: str) -> str:
        samples = self._draw_samples(question)
        if not samples:
            return self._last_resort(question)
        unique = self._dedupe(samples)
        exec_results = self._execute_all(unique)
        return self._vote(unique, exec_results)

    # ------------------------------------------------------------------ #
    # stage 1: draw multiple candidates from the frozen solver           #
    # ------------------------------------------------------------------ #

    def _draw_samples(self, question: str) -> List[Tuple[str, int]]:
        """Return [(normalized_sql, sample_index), ...] from K solver calls."""
        samples: List[Tuple[str, int]] = []
        counts: Dict[str, int] = {}
        for i in range(self.SAMPLES):
            if i == 0:
                prompt = self._build_prompt(question)
                temperature = 0.0
            else:
                nudge = self.SAMPLE_NUDGES[(i - 1) % len(self.SAMPLE_NUDGES)]
                prompt = self._build_prompt(question, nudge)
                temperature = self.SAMPLE_TEMPERATURE
            text = self._call_llm(prompt, temperature)
            sql = self._normalize(bridge.extract_sql(text))
            if not sql:
                continue
            samples.append((sql, i))
            counts[sql] = counts.get(sql, 0) + 1
            if counts[sql] >= self.EARLY_STOP_AGREEMENT:
                break  # strong consensus already; save solver calls
        return samples

    def _build_prompt(self, question: str, nudge: str = "") -> str:
        prompt = (
            "Database schema:\n%s\n\nQuestion: %s\n\n"
            "Write one SQLite SELECT query that answers the question. "
            "Respond with the SQL statement only." % (self.schema, question)
        )
        if nudge:
            prompt += "\nHint: %s" % nudge
        return prompt

    def _call_llm(self, prompt: str, temperature: float) -> str:
        try:
            raw = self.llm(
                prompt,
                system=self.SYSTEM_PROMPT,
                temperature=temperature,
                n=1,
            )
        except TypeError:
            # Very defensive: tolerate a solver that rejects the kwargs.
            try:
                raw = self.llm(prompt, system=self.SYSTEM_PROMPT)
            except Exception:
                return ""
        except Exception:
            return ""
        return self._as_text(raw)

    # ------------------------------------------------------------------ #
    # stage 2: normalize / deduplicate                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize(sql) -> str:
        if not sql:
            return ""
        s = " ".join(str(sql).split())
        while s.endswith(";"):
            s = s.rstrip(";").rstrip()
        return s

    @staticmethod
    def _as_text(raw) -> str:
        if raw is None:
            return ""
        if isinstance(raw, (list, tuple)):
            return P2P2BGlmS0G3._as_text(raw[0]) if raw else ""
        return str(raw)

    def _dedupe(
        self, samples: List[Tuple[str, int]]
    ) -> "OrderedDict[str, Dict[str, int]]":
        unique: "OrderedDict[str, Dict[str, int]]" = OrderedDict()
        for sql, idx in samples:
            info = unique.get(sql)
            if info is None:
                unique[sql] = {"count": 1, "first": idx}
            else:
                info["count"] += 1
                if idx < info["first"]:
                    info["first"] = idx
        return unique

    # ------------------------------------------------------------------ #
    # stage 3: execute every distinct candidate                          #
    # ------------------------------------------------------------------ #

    def _execute_all(self, unique: "OrderedDict[str, Dict[str, int]]") -> Dict[str, Dict]:
        results: Dict[str, Dict] = {}
        for sql in unique:
            if not self._is_readonly(sql):
                results[sql] = {
                    "ok": False,
                    "rows": [],
                    "error": "skipped: not a read-only SELECT/WITH statement",
                }
                continue
            try:
                res = self.execute(sql)
            except Exception as exc:  # a bad SQL must never kill the vote
                res = {"ok": False, "rows": [], "error": str(exc)}
            if not isinstance(res, dict):
                res = {"ok": False, "rows": [], "error": "unexpected execute() result"}
            results[sql] = res
        return results

    @staticmethod
    def _is_readonly(sql: str) -> bool:
        head = sql.lstrip().lower()
        return head.startswith(("select", "with", "values"))

    # ------------------------------------------------------------------ #
    # stage 4: vote over execution outcomes                              #
    # ------------------------------------------------------------------ #

    def _vote(self, unique: "OrderedDict[str, Dict[str, int]]", exec_results: Dict[str, Dict]) -> str:
        clusters: Dict[str, Dict] = {}
        for sql, info in unique.items():
            res = exec_results.get(sql, {})
            if not res.get("ok"):
                continue
            rows = self._as_rows(res.get("rows"))
            sig = self._signature(rows)
            cluster = clusters.get(sig)
            if cluster is None:
                clusters[sig] = {
                    "count": info["count"],
                    "first": info["first"],
                    "rep": sql,
                    "nonempty": bool(rows),
                }
            else:
                cluster["count"] += info["count"]
                cluster["nonempty"] = cluster["nonempty"] or bool(rows)
                if info["first"] < cluster["first"]:
                    cluster["first"] = info["first"]
                    cluster["rep"] = sql

        if clusters:
            winner = max(
                clusters.values(),
                key=lambda c: (c["count"], 1 if c["nonempty"] else 0, -c["first"]),
            )
            self._record_stats(unique, exec_results, clusters, winner["rep"])
            return winner["rep"]

        # Nothing executed: plurality vote on the SQL text itself.
        fallback_sql, _ = max(
            unique.items(),
            key=lambda kv: (kv[1]["count"], -kv[1]["first"]),
        )
        self._record_stats(unique, exec_results, clusters, fallback_sql)
        return fallback_sql

    @staticmethod
    def _as_rows(rows) -> List:
        if rows is None:
            return []
        if isinstance(rows, (list, tuple)):
            return list(rows)
        try:
            return list(rows)
        except Exception:
            return []

    def _signature(self, rows: List) -> str:
        """Canonical, order-insensitive fingerprint of a result set."""
        canon_rows = []
        for row in rows:
            if isinstance(row, dict):
                item = "\x1f".join(
                    "%s=%s" % (str(k), self._canon_value(v))
                    for k, v in sorted(row.items(), key=lambda kv: str(kv[0]))
                )
            elif isinstance(row, (list, tuple)):
                item = "\x1f".join(self._canon_value(v) for v in row)
            else:
                item = self._canon_value(row)
            canon_rows.append(item)
        canon_rows.sort()
        return "\x1e".join(canon_rows[: self.SIGNATURE_ROW_LIMIT])

    @staticmethod
    def _canon_value(value) -> str:
        if value is None:
            return "\x00null"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (bytes, bytearray)):
            return value.decode("utf-8", "replace")
        if isinstance(value, (int, float)):
            try:
                num = float(value)
            except (OverflowError, ValueError):
                return str(value).strip()
            if num != num or num in (float("inf"), float("-inf")):
                return repr(num)
            if num == int(num) and abs(num) < 1e15:
                return str(int(num))
            return repr(round(num, 6))
        return str(value).strip()

    # ------------------------------------------------------------------ #
    # safety net and diagnostics                                         #
    # ------------------------------------------------------------------ #

    def _last_resort(self, question: str) -> str:
        """Every sample failed to yield SQL: one final greedy attempt."""
        text = self._call_llm(self._build_prompt(question), 0.0)
        sql = self._normalize(bridge.extract_sql(text))
        return sql or "SELECT 1"

    def _record_stats(self, unique, exec_results, clusters, winner) -> None:
        try:
            self.last_stats = {
                "num_samples": sum(info["count"] for info in unique.values()),
                "num_distinct": len(unique),
                "num_executed_ok": sum(
                    1 for r in exec_results.values() if r.get("ok")
                ),
                "num_result_clusters": len(clusters),
                "winner": winner,
            }
        except Exception:
            pass  # diagnostics must never break the harness


__all__ = ["P2P2BGlmS0G3"]