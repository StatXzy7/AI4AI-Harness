"""Draw multiple SQL samples and select the best one using execution success and result agreement."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS0G0(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        system = (
            "You are an expert Text-to-SQL assistant. "
            "Return exactly one valid SQL query that answers the question. "
            "Output only SQL, without explanation or Markdown."
        )
        prompt = (
            f"Schema:\n{schema}\n\n"
            f"Question:\n{question}\n\n"
            "Generate one SQL query. Output only the SQL."
        )

        samples = []
        for temperature in (0.0, 0.3, 0.6):
            raw = self._call_llm(prompt, system=system, temperature=temperature)
            sql = self._extract_sql(raw)
            if not sql and self._looks_like_sql(raw):
                sql = raw.strip()
            if sql:
                samples.append(sql)

        if not samples:
            return ""

        candidates = {}
        order = 0
        for sql in samples:
            norm = self._normalize_sql(sql)
            if not norm:
                continue

            if norm not in candidates:
                candidates[norm] = {
                    "sql": sql,
                    "norm": norm,
                    "votes": 0,
                    "order": order,
                    "ok": False,
                    "fingerprint": "",
                }
                order += 1

            candidates[norm]["votes"] += 1

        if not candidates:
            return samples[0]

        result_support = {}
        for candidate in candidates.values():
            result = self._execute_sql(candidate["sql"])
            candidate["ok"] = bool(result.get("ok"))

            if candidate["ok"]:
                rows = result.get("rows")
                candidate["fingerprint"] = self._result_fingerprint(rows)
                result_support[candidate["fingerprint"]] = (
                    result_support.get(candidate["fingerprint"], 0)
                    + candidate["votes"]
                )

        candidate_list = list(candidates.values())
        valid = [candidate for candidate in candidate_list if candidate["ok"]]

        if valid:
            best = max(
                valid,
                key=lambda candidate: (
                    result_support.get(candidate["fingerprint"], 0),
                    candidate["votes"],
                    -candidate["order"],
                ),
            )
        else:
            best = max(
                candidate_list,
                key=lambda candidate: (
                    candidate["votes"],
                    -candidate["order"],
                ),
            )

        final_sql = self._extract_sql(best["sql"]) or best["sql"]
        return final_sql.strip()

    def _call_llm(self, prompt, system="", temperature=0.0, n=1):
        try:
            response = self.llm(prompt, system=system, temperature=temperature, n=n)
        except Exception:
            return ""

        if isinstance(response, list):
            return str(response[0]) if response else ""

        return str(response) if response is not None else ""

    def _extract_sql(self, text):
        if not text:
            return ""

        try:
            extracted = bridge.extract_sql(text)
        except Exception:
            extracted = ""

        return (extracted or "").strip()

    def _execute_sql(self, sql):
        if not sql or not sql.strip():
            return {"ok": False, "rows": [], "error": "Empty SQL"}

        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return result

        return {"ok": False, "rows": [], "error": "Unexpected execute result"}

    def _normalize_sql(self, sql):
        return " ".join((sql or "").lower().split())

    def _looks_like_sql(self, text):
        if not text:
            return False

        lowered = text.lower()
        return (
            lowered.strip().startswith(("select", "with", "insert", "update", "delete"))
            or "select" in lowered
        )

    def _result_fingerprint(self, rows):
        try:
            if isinstance(rows, list):
                return f"len={len(rows)};preview={rows[:20]!r}"[:2000]
            return repr(rows)[:2000]
        except Exception:
            return "unprintable-rows"