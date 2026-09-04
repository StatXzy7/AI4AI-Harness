"""Generate multiple SQL candidates with varied prompts and select the best executable candidate by execution-based voting."""
# MECHANISM: vote
import re

from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS2G2(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are an expert text-to-SQL engine. "
            "Return only a single valid SQL query, with no explanation."
        )
        base_prompt = f"Schema:\n{self.schema}\n\nQuestion: {question}\n"

        prompts = [
            base_prompt + "\nWrite the SQL query that answers the question. Output only SQL.",
            base_prompt
            + (
                "\nIdentify the needed tables, columns, joins, filters, and aggregations, "
                "then output the final SQL. Keep the final output to SQL only."
            ),
            base_prompt
            + (
                "\nWrite the simplest valid SQL query that answers the question. "
                "Prefer explicit joins and exact schema column names. Output only SQL."
            ),
        ]

        candidates = []
        seen = set()

        for prompt in prompts:
            raw = self.llm(prompt, system=system, temperature=0.0, n=1)
            text = self._text(raw)

            sql = bridge.extract_sql(text)
            if not sql:
                sql = self._fallback_sql(text)

            sql = self._normalize_sql(sql)
            if not sql:
                continue

            key = " ".join(sql.lower().split())
            if key in seen:
                continue

            seen.add(key)
            candidates.append(sql)

        if not candidates:
            raw = self.llm(base_prompt + "\nSQL:", system=system, temperature=0.0, n=1)
            text = self._text(raw)
            sql = bridge.extract_sql(text) or self._fallback_sql(text)
            return self._normalize_sql(sql)

        evaluated = []
        for idx, sql in enumerate(candidates):
            try:
                result = self.execute(sql)
            except Exception as exc:
                result = {"ok": False, "rows": [], "error": str(exc)}

            if not isinstance(result, dict):
                result = {
                    "ok": bool(result),
                    "rows": getattr(result, "rows", []),
                    "error": getattr(result, "error", ""),
                }

            evaluated.append((idx, sql, result))

        ok_candidates = [item for item in evaluated if item[2].get("ok")]

        if ok_candidates:
            groups = {}
            for idx, sql, result in ok_candidates:
                signature = self._execution_signature(result.get("rows"))
                groups.setdefault(signature, []).append((idx, sql))

            best_sql = None
            best_score = None

            for items in groups.values():
                rep_idx, rep_sql = min(items, key=lambda item: (len(item[1]), item[0]))
                score = (len(items), -len(rep_sql), -rep_idx)

                if best_score is None or score > best_score:
                    best_score = score
                    best_sql = rep_sql

            return best_sql

        return min(enumerate(candidates), key=lambda item: (len(item[1]), item[0]))[1]

    def _text(self, raw) -> str:
        if raw is None:
            return ""

        if isinstance(raw, (list, tuple)):
            return self._text(raw[0]) if raw else ""

        if isinstance(raw, dict):
            for key in ("text", "content", "completion", "message", "choices"):
                if key in raw:
                    return self._text(raw[key])
            return str(raw)

        return str(raw)

    def _fallback_sql(self, text: str) -> str:
        if not text:
            return ""

        matches = re.findall(
            r"