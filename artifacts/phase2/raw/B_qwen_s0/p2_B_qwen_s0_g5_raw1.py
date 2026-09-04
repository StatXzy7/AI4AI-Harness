"""Sample multiple SQL candidates and select the best executable query by result consensus."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS0G5(SQLHarness):
    def solve(self, question: str) -> str:
        system = (
            "You are an expert SQL generator. Produce a single valid SQL query that answers the question. "
            "Return only SQL, no explanation."
        )
        prompt = (
            "Given the database schema below, write one SQL query that answers the question.\n\n"
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Return only the SQL query."
        )

        candidates = []
        temperatures = [0.0, 0.3, 0.7]

        for idx, temperature in enumerate(temperatures):
            raw = self._call_llm(prompt, system, temperature)
            sql = self._extract_sql(raw)
            if not sql:
                continue

            candidates.append(
                {
                    "index": idx,
                    "temperature": temperature,
                    "sql": sql,
                    "norm": self._normalize_sql(sql),
                }
            )

        if not candidates:
            candidates.append(
                {
                    "index": 0,
                    "temperature": 0.0,
                    "sql": "SELECT 1",
                    "norm": self._normalize_sql("SELECT 1"),
                }
            )

        exec_cache = {}
        for candidate in candidates:
            norm = candidate["norm"]
            if norm not in exec_cache:
                result = self._execute_safe(candidate["sql"])
                ok = bool(result.get("ok"))
                rows = result.get("rows", [])
                exec_cache[norm] = {
                    "ok": ok,
                    "rows": rows,
                    "error": result.get("error", ""),
                    "signature": self._result_signature(rows) if ok else "__error__",
                }
            candidate.update(exec_cache[norm])

        ok_candidates = [c for c in candidates if c.get("ok")]
        if not ok_candidates:
            return min(candidates, key=lambda c: (len(c["sql"]), c["index"]))["sql"]

        signature_votes = {}
        for candidate in ok_candidates:
            signature = candidate.get("signature", "")
            signature_votes[signature] = signature_votes.get(signature, 0) + 1

        def signature_score(signature: str):
            count = signature_votes[signature]
            nonempty = any(
                c.get("rows")
                for c in ok_candidates
                if c.get("signature") == signature
            )
            return (count, nonempty, -len(signature))

        best_signature = max(signature_votes, key=signature_score)
        best_pool = [
            c for c in ok_candidates if c.get("signature") == best_signature
        ]

        best = min(
            best_pool,
            key=lambda c: (not c.get("rows"), len(c["sql"]), c["index"]),
        )
        return best["sql"]

    def _call_llm(self, prompt: str, system: str, temperature: float):
        try:
            return self.llm(prompt, system=system, temperature=temperature, n=1)
        except Exception:
            try:
                return self.llm(prompt, system=system, n=1)
            except Exception:
                try:
                    return self.llm(prompt)
                except Exception:
                    return ""

    def _extract_sql(self, text) -> str:
        if text is None:
            return ""

        if isinstance(text, (list, tuple)):
            text = text[0] if text else ""

        text = str(text)

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = ""

        sql = (sql or "").strip()
        if sql:
            return sql

        stripped = text.strip()
        upper = stripped.upper()
        if any(keyword in upper for keyword in ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")):
            return stripped

        return ""

    def _normalize_sql(self, sql: str) -> str:
        return " ".join((sql or "").strip().lower().split())

    def _execute_safe(self, sql: str):
        try:
            result = self.execute(sql)
            if isinstance(result, dict):
                return result
            return {"ok": bool(result), "rows": [], "error": ""}
        except Exception as exc:
            return {"ok": False, "rows": [], "error": f"Execution exception: {exc}"}

    def _result_signature(self, rows) -> str:
        if rows is None:
            return "null"

        try:
            if isinstance(rows, (list, tuple)):
                return repr(sorted(repr(row) for row in rows))
            return repr(rows)
        except Exception:
            try:
                return str(rows)
            except Exception:
                return "unrepresentable"