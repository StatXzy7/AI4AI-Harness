"""Generate multiple candidate SQL queries and select the most consistent executable result."""
# MECHANISM: vote
from ..harness_base import SQLHarness
from .. import bridge


class P2P2BQwenS0G4(SQLHarness):
    def solve(self, question: str) -> str:
        schema = getattr(self, "schema", "") or ""
        question = (question or "").strip()

        base = (
            "Given the following database schema and natural language question, "
            "produce one SQL query.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Question: {question}\n"
        )

        variants = [
            (
                "You are a precise SQL expert. Return only one valid SQL query, without explanation.",
                base + "Write the SQL query that answers the question.",
            ),
            (
                "You are a careful database engineer. Briefly identify tables, joins, filters, then give the final SQL.",
                base + "Reason briefly, then output the final SQL query.",
            ),
            (
                "You are a strict SQL generator. Use only tables and columns present in the schema.",
                base + "Use only existing schema names and produce the final SQL query.",
            ),
        ]

        candidates = []
        for system, prompt in variants:
            raw = self._call_llm(prompt, system)
            sql = self._extract_sql(raw)
            if not sql:
                continue

            candidates.append(
                {
                    "sql": sql,
                    "norm_sql": " ".join(sql.split()).lower(),
                }
            )

        if not candidates:
            raw = self._call_llm(
                base + "SQL:",
                "You are a SQL expert. Return only one valid SQL query.",
            )
            fallback = self._extract_sql(raw)
            return fallback or "SELECT 1"

        exec_cache = {}
        for cand in candidates:
            key = cand["norm_sql"]
            if key in exec_cache:
                result = exec_cache[key]
            else:
                result = self._execute_sql(cand["sql"])
                exec_cache[key] = result

            cand["ok"] = bool(result.get("ok"))
            cand["rows"] = result.get("rows", []) if cand["ok"] else []
            cand["error"] = result.get("error", "") if not cand["ok"] else ""
            cand["signature"] = self._signature(cand["rows"]) if cand["ok"] else None

        ok_candidates = [c for c in candidates if c["ok"]]
        if ok_candidates:
            groups = {}
            for idx, cand in enumerate(ok_candidates):
                groups.setdefault(cand["signature"], []).append(idx)

            best_sig = None
            best_count = -1
            best_first = len(ok_candidates) + 1

            for sig, idxs in groups.items():
                first = min(idxs)
                count = len(idxs)
                if count > best_count or (count == best_count and first < best_first):
                    best_sig = sig
                    best_count = count
                    best_first = first

            chosen = ok_candidates[min(groups[best_sig])]
            return chosen["sql"]

        return candidates[0]["sql"]

    def _call_llm(self, prompt: str, system: str) -> str:
        try:
            response = self.llm(prompt, system=system, temperature=0.0, n=1)
        except Exception:
            return ""
        return self._response_text(response)

    def _response_text(self, response) -> str:
        if response is None:
            return ""

        if isinstance(response, str):
            return response

        if isinstance(response, list):
            for item in response:
                text = self._response_text(item)
                if text:
                    return text
            return ""

        if isinstance(response, dict):
            for key in ("text", "completion", "content", "message", "output"):
                if key in response:
                    text = self._response_text(response[key])
                    if text:
                        return text

            if "choices" in response:
                return self._response_text(response["choices"])

            if "messages" in response:
                return self._response_text(response["messages"])

        for attr in ("text", "content"):
            if hasattr(response, attr):
                return self._response_text(getattr(response, attr))

        return str(response)

    def _extract_sql(self, text: str) -> str:
        if not text:
            return ""

        try:
            sql = bridge.extract_sql(text)
        except Exception:
            sql = text

        return (sql or text).strip()

    def _execute_sql(self, sql: str) -> dict:
        try:
            result = self.execute(sql)
        except Exception as exc:
            return {"ok": False, "rows": [], "error": str(exc)}

        if isinstance(result, dict):
            return result

        return {"ok": bool(result), "rows": [], "error": ""}

    def _signature(self, rows) -> str:
        try:
            normalized = []

            for row in rows or []:
                if isinstance(row, dict):
                    normalized.append(
                        tuple(
                            sorted(
                                (str(k), self._normalize_value(v))
                                for k, v in row.items()
                            )
                        )
                    )
                elif hasattr(row, "keys"):
                    normalized.append(
                        tuple(
                            sorted(
                                (str(k), self._normalize_value(row[k]))
                                for k in row.keys()
                            )
                        )
                    )
                elif isinstance(row, (list, tuple)):
                    normalized.append(
                        tuple(self._normalize_value(v) for v in row)
                    )
                else:
                    try:
                        normalized.append(
                            tuple(self._normalize_value(v) for v in row)
                        )
                    except Exception:
                        normalized.append((self._normalize_value(row),))

            try:
                return repr(sorted(normalized, key=repr))
            except Exception:
                return repr(normalized)
        except Exception:
            return repr(rows)

    def _normalize_value(self, value):
        if isinstance(value, float):
            try:
                return round(value, 6)
            except Exception:
                return value

        if isinstance(value, bytes):
            try:
                return value.decode("utf-8", "ignore")
            except Exception:
                return repr(value)

        return value