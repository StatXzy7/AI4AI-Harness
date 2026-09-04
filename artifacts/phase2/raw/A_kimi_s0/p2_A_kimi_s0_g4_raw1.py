"""Self-consistency voting: sample several candidate SQL queries at temperature, execute each, and return the query whose execution result set forms the largest majority cluster."""
# MECHANISM: vote        -- you draw multiple samples and select among them
from collections import Counter

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AKimiS0G4(SQLHarness):
    NUM_SAMPLES = 7
    SAMPLE_TEMPERATURE = 0.7
    MAX_EXECUTIONS = 10

    def solve(self, question: str) -> str:
        prompt = (
            "You are given a SQLite database schema and a natural-language question.\n"
            "Write one SQL query that answers the question correctly.\n"
            "Return only the SQL query, with no explanation or markdown.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )

        raw_outputs = self._sample_candidates(prompt)
        candidates = self._dedupe(self._extract(raw_outputs))

        if not candidates:
            return ""

        # Execution-guided clustering: group candidates by the result set they
        # produce, then let the largest cluster win the vote.
        clusters = {}
        for sql in candidates[: self.MAX_EXECUTIONS]:
            try:
                outcome = self.execute(sql)
            except Exception:
                continue
            if not isinstance(outcome, dict) or not outcome.get("ok"):
                continue
            key = self._rows_key(outcome.get("rows"))
            clusters.setdefault(key, []).append(sql)

        if clusters:
            winners = max(clusters.values(), key=len)
            return self._textual_majority(winners)

        # No candidate executed cleanly: fall back to a pure textual vote.
        return self._textual_majority(candidates)

    def _sample_candidates(self, prompt: str):
        outputs = []
        for i in range(self.NUM_SAMPLES):
            temperature = 0.0 if i == 0 else self.SAMPLE_TEMPERATURE
            try:
                out = self.llm(
                    prompt,
                    system="You are an expert SQLite query generator.",
                    temperature=temperature,
                    n=1,
                )
            except TypeError:
                try:
                    out = self.llm(prompt)
                except Exception:
                    continue
            except Exception:
                continue
            if isinstance(out, (list, tuple)):
                outputs.extend(str(o) for o in out if o)
            elif out:
                outputs.append(str(out))
        return outputs

    def _extract(self, outputs):
        sqls = []
        for text in outputs:
            sql = ""
            try:
                sql = bridge.extract_sql(text)
            except Exception:
                sql = ""
            if not sql:
                sql = text
            sql = sql.strip().rstrip(";").strip()
            if sql:
                sqls.append(sql)
        return sqls

    def _dedupe(self, sqls):
        seen = set()
        unique = []
        for sql in sqls:
            key = self._normalize(sql)
            if key in seen:
                continue
            seen.add(key)
            unique.append(sql)
        return unique

    def _textual_majority(self, sqls) -> str:
        counts = Counter(self._normalize(s) for s in sqls)
        best_key, _ = max(counts.items(), key=lambda kv: (kv[1], -sqls_index(sqls, kv[0], self._normalize)))
        for sql in sqls:
            if self._normalize(sql) == best_key:
                return sql
        return sqls[0]

    @staticmethod
    def _normalize(sql: str) -> str:
        return " ".join(sql.lower().split())

    @staticmethod
    def _rows_key(rows):
        if rows is None:
            return ("__no_rows__",)
        try:
            rendered = sorted(repr(r) for r in rows)
            return tuple(rendered)
        except Exception:
            return (repr(rows),)


def sqls_index(sqls, key, normalize):
    for idx, sql in enumerate(sqls):
        if normalize(sql) == key:
            return idx
    return len(sqls)