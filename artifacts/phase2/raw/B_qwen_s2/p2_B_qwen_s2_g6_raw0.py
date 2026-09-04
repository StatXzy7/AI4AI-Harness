"""Draw multiple SQL candidates and select among them using execution success and result consensus."""
# MECHANISM: vote

from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS2G6(SQLHarness):
    def solve(self, question: str) -> str:
        base_prompt = (
            "Use the following database schema to answer the question.\n"
            "Return exactly one valid SQL query and nothing else.\n"
            "Do not wrap the SQL in markdown.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "SQL:"
        )

        variants = [
            (
                base_prompt,
                "You are an expert text-to-SQL system. Output only SQL.",
                0.0,
            ),
            (
                base_prompt + "\nDouble-check join keys, filters, and aggregation before answering.",
                "You are a careful SQL engineer. Output only SQL.",
                0.0,
            ),
            (
                base_prompt + "\nPrefer simple, executable SQL that directly answers the question.",
                "You are a precise SQL generator. Output only SQL.",
                0.0,
            ),
        ]

        candidates = []
        seen_sql = set()
        fallback_text = ""

        for prompt, system, temperature in variants:
            try:
                raw = self.llm(prompt, system=system, temperature=temperature, n=1)
            except Exception:
                continue

            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            raw = str(raw)

            if not fallback_text and raw.strip():
                fallback_text = raw.strip()

            try:
                sql = bridge.extract_sql(raw)
            except Exception:
                sql = ""

            if not sql:
                sql = raw.strip()

            sql = sql.strip()
            if not sql:
                continue

            normalized_sql = self._normalize_sql(sql)
            if normalized_sql in seen_sql:
                continue

            seen_sql.add(normalized_sql)
            candidates.append(sql)

        if not candidates:
            return fallback_text

        successful = []
        result_counts = {}

        for sql in candidates:
            try:
                result = self.execute(sql)
            except Exception:
                continue

            if not isinstance(result, dict) or not result.get("ok"):
                continue

            rows = result.get("rows", [])
            key = self._result_key(rows)
            result_counts[key] = result_counts.get(key, 0) + 1
            successful.append((sql, key))

        if not successful:
            return candidates[0]

        best_sql = None
        best_rank = None

        for idx, (sql, key) in enumerate(successful):
            rank = (-result_counts[key], len(sql), idx)
            if best_rank is None or rank < best_rank:
                best_rank = rank
                best_sql = sql

        return best_sql or candidates[0]

    def _normalize_sql(self, sql: str) -> str:
        text = sql.strip().rstrip(";")
        text = " ".join(text.split())
        return text.lower()

    def _result_key(self, rows) -> str:
        try:
            row_list = list(rows)
        except TypeError:
            return repr(rows)[:2000]

        limited = row_list[:200]
        parts = []

        for row in limited:
            parts.append(repr(row))

        parts.sort()
        key = f"{len(row_list)}|" + "|".join(parts)
        return key[:4000]