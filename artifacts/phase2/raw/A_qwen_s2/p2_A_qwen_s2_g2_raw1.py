"""Samples multiple SQL candidates and selects one by execution success and result consensus."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2AQwenS2G2(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are an expert Text-to-SQL system. "
            "Answer with one executable SQL query only."
        )
        prompt = (
            "Use the database schema below to answer the question with one SQL query.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question:\n{question}\n\n"
            "Return only SQL."
        )

        candidates = []
        seen = set()
        last_text = ""
        sample_count = 3
        temperatures = [0.0, 0.4, 0.8]

        for i in range(sample_count):
            temperature = temperatures[i] if i < len(temperatures) else 0.7
            raw = self.llm(prompt, system=system, temperature=temperature, n=1)
            text = self._to_text(raw)
            last_text = text or last_text

            try:
                sql = bridge.extract_sql(text).strip()
            except Exception:
                sql = ""

            if not sql:
                sql = self._fallback_sql(text)

            if not sql:
                continue

            normalized = " ".join(sql.lower().split())
            if normalized in seen:
                continue

            seen.add(normalized)
            candidates.append(
                {
                    "sql": sql,
                    "temperature": temperature,
                    "index": len(candidates),
                    "ok": False,
                    "rows": None,
                    "error": "",
                }
            )

        if not candidates:
            return self._fallback_sql(last_text)

        successful = []
        for candidate in candidates:
            try:
                result = self.execute(candidate["sql"])
            except Exception as exc:
                candidate["error"] = f"execution exception: {exc}"
                continue

            if isinstance(result, dict) and result.get("ok"):
                candidate["ok"] = True
                candidate["rows"] = result.get("rows", [])
                successful.append(candidate)
            else:
                error = (
                    result.get("error", "unknown execution error")
                    if isinstance(result, dict)
                    else "unexpected execution result"
                )
                candidate["error"] = str(error)

        if not successful:
            return candidates[0]["sql"]

        votes = {}
        for candidate in successful:
            key = self._result_key(candidate.get("rows"))
            candidate["result_key"] = key
            votes[key] = votes.get(key, 0) + 1

        def score(candidate):
            vote_count = votes.get(candidate.get("result_key"), 0)
            non_empty = 1 if candidate.get("rows") else 0
            return (
                vote_count,
                non_empty,
                -candidate["temperature"],
                -candidate["index"],
            )

        best = max(successful, key=score)
        return best["sql"]

    def _to_text(self, raw):
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        if isinstance(raw, (list, tuple)):
            return self._to_text(raw[0]) if raw else ""
        if isinstance(raw, dict):
            for key in ("text", "completion", "content", "message", "response", "output"):
                if key in raw:
                    return self._to_text(raw[key])
        return str(raw)

    def _fallback_sql(self, text):
        text = str(text or "").strip()
        if not text:
            return ""
        return text[:2000]

    def _result_key(self, rows):
        try:
            if rows is None:
                return ("none", 0)

            if isinstance(rows, list):
                limited = rows[:100]
                normalized = [self._normalize_value(row) for row in limited]

                try:
                    normalized.sort()
                except Exception:
                    pass

                return ("rows", len(rows), tuple(normalized))

            return ("scalar", str(rows)[:1000])
        except Exception:
            return ("opaque", str(rows)[:1000])

    def _normalize_value(self, value):
        try:
            if isinstance(value, dict):
                return tuple(
                    sorted((str(k), self._normalize_value(v)) for k, v in value.items())
                )

            if isinstance(value, (list, tuple, set)):
                return tuple(self._normalize_value(item) for item in value)

            return str(value)
        except Exception:
            return str(value)