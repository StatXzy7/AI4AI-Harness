"""Sample multiple SQL candidates and select the best executable query by self-consistency voting."""
# MECHANISM: vote
from collections import Counter
import json

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BDeepseekS0G5(SQLHarness):
    N_SAMPLES = 5
    TEMPERATURE = 0.3

    def solve(self, question: str) -> str:
        schema = self.schema
        system = "You are an expert SQLite developer. Return only a single SQL query."

        prompt = (
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n\n"
            f"Write a SQL query to answer the question."
        )

        raw_samples = self._llm_samples(prompt, system)
        candidates = []
        for raw in raw_samples:
            text = str(raw).strip() if raw is not None else ""
            try:
                sql = bridge.extract_sql(text)
            except Exception:
                sql = ""
            if not sql:
                sql = text
            if sql:
                candidates.append(sql)

        if not candidates:
            return ""

        # Execute each candidate and keep those that succeed.
        successful = []
        for sql in candidates:
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                successful.append((sql, self._rows_key(result.get("rows", []))))

        if successful:
            # Vote by the returned result set: queries that agree on the result are
            # more likely to be correct.
            counts = Counter(key for _, key in successful)
            best_key, _ = counts.most_common(1)[0]
            for sql, key in successful:
                if key == best_key:
                    return sql

        # If no candidate executes, fall back to a string-level majority vote.
        normalized = [self._normalize_sql(sql) for sql in candidates]
        if normalized:
            counts = Counter(normalized)
            best_norm, _ = counts.most_common(1)[0]
            for sql, norm in zip(candidates, normalized):
                if norm == best_norm:
                    return sql

        return candidates[0]

    def _llm_samples(self, prompt: str, system: str):
        raw = self.llm(prompt, system=system, temperature=self.TEMPERATURE, n=self.N_SAMPLES)
        if isinstance(raw, list):
            return [item for item in raw if item is not None]
        return [raw]

    def _normalize_sql(self, sql: str) -> str:
        return " ".join(sql.strip().rstrip(";").strip().split())

    def _rows_key(self, rows):
        try:
            sorted_rows = sorted(
                rows,
                key=lambda row: json.dumps(row, sort_keys=True, default=str)
            )
            return json.dumps(sorted_rows, sort_keys=True, default=str)
        except Exception:
            return repr(rows)